import numpy as np

from deeplearning.tensor import Tensor
from deeplearning.layers import Layer
from deeplearning.func import tanh,tanh_derivative,sigmoid,sigmoid_derivative

"""
    https://iamtrask.github.io/2015/11/15/anyone-can-code-lstm/
    http://manutdzou.github.io/2016/07/11/RNN-backpropagation.html
    
    https://github.com/mklissa/CS231n/tree/master/assignment3/cs231n
"""


class LastTimeStep(Layer):
    def __init__(self, name):
        """
            Forwarding the last time_step of the output to the next layer.
        """
        super().__init__(name)
    
    def forward(self, inputs, **kwargs):
        self.input_shape = inputs.shape
        return inputs[:,-1,:]
    
    def backward(self, grad):
        dx = np.zeros(self.input_shape)
        dx[:,-1,:] = grad
        return dx


class RNN_Cell(Layer):
    def __init__(self, name, D, H):
        super().__init__(name)
        
        self.D = D
        self.H = H

        self.params["Wxh"] = np.random.randn(D, H) / np.sqrt(D / 2.)
        self.params["Whh"] = np.random.randn(H, H) / np.sqrt(H / 2.)
        self.params["bh"] = np.zeros((1,H))
    
    

    def forward(self, inputs, **kwargs):
        state = kwargs["cache"]
        
        Wxh, Whh = self.params['Wxh'], self.params['Whh']
        bh = self.params['bh']

        h_previous = state.copy()

        gate_input = inputs @ Wxh + h_previous @ Whh + bh
        cache = (gate_input, inputs, h_previous)
        
        return gate_input, cache


    def backward(self, grad, **kwargs):
        Wxh, Whh = self.params['Wxh'], self.params['Whh']
        bh = self.params['bh']
        gate_input, inputs, h_previous = kwargs["cache"]
        
        dinputs =  grad @ Wxh.T
        
        self.grads["Wxh"] = inputs.T @ grad
        self.grads["Whh"] = h_previous.T @ grad
        self.grads["bh"] = np.sum(grad,axis=0)
    
        dprev_h = grad @ Whh.T
        
        return dinputs, dprev_h



class RNN(Layer):
    def __init__(self, name, D, H):
        """
            Contains one rnn cell and get output by "forwarding" the cell recurrently.
            
            Params:
            ---------------
            D: input size (size of the last dimension of the input matrix)
            
            H: size of hidden layer
        """
        super().__init__(name)
        
        self.D = D
        self.H = H

        self.rnn_cell = RNN_Cell(name,D,H)


    def forward(self, inputs, **kwargs):
        N,T,_ = inputs.shape
        self.N = N
        self.T = T
        
        H = self.H
        
        # initialize some caches
        h = np.zeros((N,T,H))
        h0 = np.zeros((N,H))
        self.time_cache = [None for i in range(T)]

        prev_h = h0
        
        # iterate from the first cell to the last one (actually, the same one, because they share weights)
        for t in range(T):
            next_h,self.time_cache[t] = self.rnn_cell.forward(inputs[:,t,:].squeeze(),cache=(prev_h))
            h[:,t,:] = next_h
            prev_h = next_h
        
        # the output seems like (batch_size, time_steps, size_of_hidden_layer)
        # for some classification problems, just using the last time_step, aka, h[:,-1,:]
        return h

    def backward(self, grad):
        N,D,T,H = self.N,self.D, self.T, self.H
        
        # initialization
        dWxh = np.zeros((D, H))
        dWhh = np.zeros((H, H))
        dbh = np.zeros((H))
        dx = np.zeros((N, T, D))
        dprev_h_t = np.zeros((N,H))
        
        # back-prop with respect to the time step
        for t in reversed(range(T)):
            dx[:,t,:], dprev_h_t = self.rnn_cell.backward(grad[:,t,:] + dprev_h_t, cache=self.time_cache[t])
            dWxh += self.rnn_cell.grads["Wxh"]
            dWhh += self.rnn_cell.grads["Whh"]
            dbh += self.rnn_cell.grads["bh"]

        dh0 = dprev_h_t

        self.rnn_cell.grads["Wxh"] = dWxh
        self.rnn_cell.grads["Whh"] = dWhh
        self.rnn_cell.grads["bh"] = dbh

        return dx


    def get_params_grads(self):
        """
            return  (name in the map of optimizer, real param name, param)
        """
        for map_name,name, param, grad in self.rnn_cell.get_params_grads():
            yield self.name+'_'+map_name, name, param, grad




"""
    Preparation for LSTM:
    
    http://colah.github.io/posts/2015-08-Understanding-LSTMs/
"""


class LSTM_Cell(RNN_Cell):
    def __init__(self, name, D, H):
        super().__init__(name, D, H)
    
        # Wi Wf Wo Wg => the shape of weights should be 4*H
        self.params["Wxh"] = np.random.randn(D, 4*H) / np.sqrt(D / 2.)
        self.params["Whh"] = np.random.randn(H, 4*H) / np.sqrt(H / 2.)
        self.params["bh"] = np.zeros((1, 4*H))
    
    
    def forward(self, inputs, **kwargs):
        prev_h, prev_c = kwargs["cache"]
        
        Wxh, Whh = self.params['Wxh'], self.params['Whh']
        bh = self.params['bh']
        
        H = self.H
        
        # compute the input of i,f,o,g in one formula
        a = inputs @ Wxh + prev_h @ Whh + bh
        
        # activate the output respectively
        
        # input layer gate, decides which value to be updated
        i = sigmoid(a[:,:H])
        
        # forget gate layer: indicates if a value in Ct-1 should be forgotten
        # 1 represents “completely keep this”
        # 0 represents “completely get rid of this.”
        f = sigmoid(a[:,H:2*H])
        
        # output gate layer: what parts of the cell state we’re going to output
        o = sigmoid(a[:,2*H:-H])
        
        # new candidate values for cell state
        g = tanh(a[:,-H:])
        
        # the new cell state
        c = f*prev_c + i*g
        
        # get output according to the cell state
        h = o * tanh(c)
        
        cache = (i, f, o, g, h, c, a, inputs, prev_h, prev_c)
        
        return h, c, cache
    
    
    def backward(self, grad, **kwargs):
        Wxh, Whh = self.params['Wxh'], self.params['Whh']
        bh = self.params['bh']
        
        H = self.H
        
        i, f, o, g, h, c, a, inputs, prev_h, prev_c = kwargs["cache"]
        
        dnext_h, dnext_c = grad
    
        # actually, the output of the cell is tuple(h,c) and c will influence both of them.
        # according to chain rule, add two derivative path together
        dc = dnext_c + dnext_h * o * tanh_derivative(c)
        di = dc * g
        df = dc * prev_c
        do = dnext_h * tanh_derivative(c)
        dg = dc * i

        da = np.zeros_like(a)
        da[:, : H] = sigmoid_derivative(a[:,:H]) * di
        da[:, H : 2*H] = sigmoid_derivative(a[:,H:2*H]) * df
        da[:, 2*H : 3*H] = sigmoid_derivative(a[:,2*H:-H]) * do
        da[:, 3*H :] = tanh_derivative(a[:,-H:]) * dg

        self.grads["Wxh"] = inputs.T @ da
        self.grads["Whh"] = prev_h.T @ da
        self.grads["bh"] = np.sum(da, axis=0)
        dh = da @ Whh.T
        dx = da @ Wxh.T

        return dx, dh, dc




class LSTM(Layer):
    def __init__(self, name, D, H):
        """
            Contains one rnn cell and get output by "forwarding" the cell recurrently.
            
            Params:
            ---------------
            D: input size (size of the last dimension of the input matrix)
            
            H: size of hidden layer
        """
        super().__init__(name)
        
        self.D = D
        self.H = H
        
        self.rnn_cell = LSTM_Cell(name,D,H)
    
    
    def forward(self, inputs, **kwargs):
        N,T,D = inputs.shape
        self.N = N
        self.T = T
        
        H = self.H
        
        # initialize some caches
        h = np.zeros((N,T,H))
        h0 = np.zeros((N,H))
        c0 = np.zeros_like(h0)
        self.time_cache = [None for i in range(T)]
        
        prev_h = h0
        prev_c = c0
        
        # iterate from the first cell to the last one (actually, the same one, because they share weights)
        for t in range(T):
            next_h, next_c, self.time_cache[t] = self.rnn_cell.forward(inputs[:,t,:].squeeze(),cache=(prev_h, prev_c))
            h[:,t,:] = next_h
            prev_h = next_h
            prev_c = next_c
        
        
        # the output seems like (batch_size, time_steps, size_of_hidden_layer)
        # for some classification problems, just using the last time_step, aka, h[:,-1,:]
        return h
    
    def backward(self, grad):
        N,D,T,H = self.N,self.D, self.T, self.H
        
        # required for initialization of dWxh,dWhh and dbh
        w_size = self.rnn_cell.params["Wxh"].shape[1]
        
        # initialization
        dWxh = np.zeros((D, w_size))
        dWhh = np.zeros((H, w_size))
        dbh = np.zeros((w_size))
        dx = np.zeros((N, T, D))
        dprev_h_t = np.zeros((N,H))
        dprev_c_t = np.zeros((N,H))
        
        # back-prop with respect to the time step
        for t in reversed(range(T)):
            dx[:,t,:], dprev_h_t, dprev_c_t = self.rnn_cell.backward(grad=(grad[:,t,:] + dprev_h_t, dprev_c_t), cache=self.time_cache[t])
            dWxh += self.rnn_cell.grads["Wxh"]
            dWhh += self.rnn_cell.grads["Whh"]
            dbh += self.rnn_cell.grads["bh"]
        
        dh0 = dprev_h_t
        
        self.rnn_cell.grads["Wxh"] = dWxh
        self.rnn_cell.grads["Whh"] = dWhh
        self.rnn_cell.grads["bh"] = dbh
        
        return dx


    def get_params_grads(self):
        """
            return  (name in the map of optimizer, real param name, param)
        """
        for map_name,name, param, grad in self.rnn_cell.get_params_grads():
            yield self.name+'_'+map_name, name, param, grad






class GRU_Cell(RNN_Cell):
    def __init__(self, name, D, H):
        super().__init__(name, D, H)
        
        # Wi Wf Wo Wg => the shape of weights should be 4*H
        self.params["Wxh"] = np.random.randn(D, 3*H) / np.sqrt(D / 2.)
        self.params["Whh"] = np.random.randn(H, 3*H) / np.sqrt(H / 2.)
        self.params["bh"] = np.zeros((1, 3*H))
    
    
    def forward(self, inputs, **kwargs):
        prev_h, prev_c = kwargs["cache"]
        self.N = inputs.shape[0]
        
        Wxh, Whh = self.params['Wxh'], self.params['Whh']
        bh = self.params['bh']
        
        H = self.H
        
        # update gate
        a_z = inputs @ Wxh[:,:H] + prev_h @ Whh[:,:H]
        z = sigmoid(a_z)
        # reset gate
        a_r = inputs @ Wxh[:,H:2*H] + prev_h @ Whh[:,H:2*H]
        r = sigmoid(a_r)
        # state
        a_c = inputs @ Wxh[:,-H:] + (r * prev_h) @ Whh[:,-H:]
        c = tanh(a_c)
        # output
        h = (1 - z) * prev_c + (z * c)
        
        cache = (a_z, a_r, a_c, z, r, c, h, inputs, prev_h, prev_c)
        
        return h, c, cache
    
    
    def backward(self, grad, **kwargs):
        Wxh, Whh = self.params['Wxh'], self.params['Whh']
        bh = self.params['bh']
        
        H = self.H
        
        a_z, a_r, a_c, z, r, c, h, inputs, prev_h, prev_c = kwargs["cache"]
        
        dnext_h, dnext_c = grad
        
        # actually, the output of the cell is tuple(h,c) and c will influence both of them.
        # according to chain rule, add two derivative path together
        dc = dnext_c + dnext_h * z
        dz = dnext_h * (-1*prev_c) + c
        da_c = dc * tanh_derivative(a_c)
        dr = da_c @ Whh[:,-H:].T * prev_h
        
        
        da = np.zeros((self.N, 3*self.H))
        da[:,0:H] = sigmoid_derivative(a_z) * dz
        da[:, H : 2*H] = sigmoid_derivative(a_r) * dr
        da[:, 2*H : 3*H] = da_c
        
        
        self.grads["Wxh"] = inputs.T @ da
        self.grads["Whh"] = np.zeros_like(self.params["Whh"])
        self.grads["Whh"][:,0:2*H] = prev_h.T @ da[:,0:2*H]
        self.grads["Whh"][:,-H:] = (prev_h*r).T @ da[:,-H:]
        self.grads["bh"] = np.sum(da, axis=0)
        dh = da_c @ Whh[:,-H:].T * r + da[:,0:2*H] @ Whh[:,0:2*H].T
        dx = da @ Wxh.T
        
        return dx, dh, dc



class GRU(LSTM):
    def __init__(self, name, D, H):
        """
            Contains one rnn cell and get output by "forwarding" the cell recurrently.
            
            Params:
            ---------------
            D: input size (size of the last dimension of the input matrix)
            
            H: size of hidden layer
            """
        super().__init__(name,D,H)
        
        self.rnn_cell = GRU_Cell(name,D,H)
