from regularizers import *
import tensorflow as tf
import math


class convLayer(object):
    filter_dimension = None
    __stride_length = None
    __activation_function = None

    weights = None
    biases = None
    activations = None

    input_size = None
    output_size = None
    name = None
    regularization_coefficient = None

    def __init__(self, name, input_size, filter_dimension, stride_length, activation_function, initializer, regularization_coefficient):
        self.name = name
        self.filter_dimension = filter_dimension
        self.__stride_length = stride_length
        self.__activation_function = activation_function
        self.input_size = input_size
        self.output_size = input_size
        self.regularization_coefficient = regularization_coefficient

        padding = 2*(math.floor(filter_dimension[0] / 2))
        self.output_size[1] = int((self.output_size[1] - filter_dimension[0] + padding) / stride_length + 1)
        padding = 2 * (math.floor(filter_dimension[1] / 2))
        self.output_size[2] = int((self.output_size[2] - filter_dimension[1] + padding) / stride_length + 1)
        self.output_size[-1] = filter_dimension[-1]

        if initializer == 'xavier':
            self.weights = tf.get_variable(self.name + '_weights',
                                           shape=self.filter_dimension,
                                           initializer=tf.contrib.layers.xavier_initializer_conv2d())
        else:
            self.weights = tf.get_variable(self.name + '_weights',
                                           shape=self.filter_dimension,
                                           initializer=tf.truncated_normal_initializer(stddev=5e-2),
                                           dtype=tf.float32)

        self.biases = tf.get_variable(self.name + '_bias',
                                      [self.output_size[-1]],
                                      initializer=tf.constant_initializer(0.1),
                                      dtype=tf.float32)

    def forwardPass(self, x, deterministic):
        # For convention, just use a symmetrical stride with same padding
        activations = tf.nn.conv2d(x, self.weights,
                                   strides=[1, self.__stride_length, self.__stride_length, 1],
                                   padding='SAME')

        activations = tf.nn.bias_add(activations, self.biases)

        # Apply a non-linearity specified by the user
        if self.__activation_function == 'relu':
            activations = tf.nn.relu(activations)

        self.activations = activations

        return activations


class poolingLayer(object):
    __kernel_size = None
    __stride_length = None

    input_size = None
    output_size = None

    def __init__(self, input_size, kernel_size, stride_length):
        self.__kernel_size = kernel_size
        self.__stride_length = stride_length
        self.input_size = input_size
        # The pooling operation will reduce the width and height dimensions
        self.output_size = self.input_size
        self.output_size[1] = int(math.floor((self.output_size[1]-kernel_size)/stride_length + 1) + 1)
        self.output_size[2] = int(math.floor((self.output_size[2]-kernel_size)/stride_length + 1) + 1)

    def forwardPass(self, x, deterministic):
        return tf.nn.max_pool(x,
                              ksize=[1, self.__kernel_size, self.__kernel_size, 1],
                              strides=[1, self.__stride_length, self.__stride_length, 1],
                              padding='SAME')


class fullyConnectedLayer(object):
    weights = None
    biases = None
    activations = None
    __activation_function = None
    __reshape = None
    regularization_coefficient = None

    shakeweight_p = None
    shakeout_p = None
    shakeout_c = None
    dropconnect_p = None

    input_size = None
    output_size = None
    name = None

    def __init__(self, name, input_size, output_size, reshape, batch_size, activation_function, initializer, regularization_coefficient):
        self.name = name
        self.input_size = input_size
        self.output_size = output_size
        self.__reshape = reshape
        self.__batch_size = batch_size
        self.__activation_function = activation_function
        self.regularization_coefficient = regularization_coefficient

        # compute the vectorized size for weights if we will need to reshape it
        if reshape:
            vec_size = input_size[1]*input_size[2]*input_size[3]
        else:
            vec_size = input_size

        if initializer == 'xavier':
            self.weights = tf.get_variable(self.name + '_weights', shape=[vec_size, output_size],
                                           initializer=tf.contrib.layers.xavier_initializer())
        else:
            self.weights = tf.get_variable(self.name + '_weights',
                                           shape=[vec_size, output_size],
                                           initializer=tf.truncated_normal_initializer(stddev=math.sqrt(2.0/self.output_size)),
                                           dtype=tf.float32)

        self.biases = tf.get_variable(self.name + '_bias',
                                      [self.output_size],
                                      initializer=tf.constant_initializer(0.1),
                                      dtype=tf.float32)

    def forwardPass(self, x, deterministic):
        # Reshape into a column vector if necessary
        if self.__reshape is True:
            x = tf.reshape(x, [self.__batch_size, -1])

        # Do special regularization operation on weights
        if not deterministic and self.shakeweight_p is not None:
            activations = regularizers.shakeWeight(x, self.weights, self.shakeweight_p)
        elif not deterministic and self.shakeout_p is not None:
            activations = regularizers.shakeOut(x, self.weights, self.shakeout_p, self.shakeout_c)
        elif not deterministic and self.dropconnect_p is not None:
            activations = regularizers.dropConnect(x, self.weights, self.dropconnect_p)
        else:
            activations = tf.matmul(x, self.weights)

        activations = tf.add(activations, self.biases)

        # Apply a non-linearity specified by the user
        if self.__activation_function == 'relu':
            activations = tf.nn.relu(activations)

        self.activations = activations

        return activations


class inputLayer(object):
    """An object representing the input layer so it can give information about input size to the next layer"""
    input_size = None
    output_size = None

    def __init__(self, input_size):
        self.input_size = input_size
        self.output_size = input_size

    def forwardPass(self, x, deterministic):
        return x


class normLayer(object):
    """Layer which performs local response normalization"""
    input_size = None
    output_size = None

    def __init__(self, input_size):
        self.input_size = input_size
        self.output_size = input_size

    def forwardPass(self, x, deterministic):
        x = tf.nn.lrn(x, bias=1.0, alpha=0.001/9.0, beta=0.75)
        return x


class dropoutLayer(object):
    """Layer which performs dropout"""
    input_size = None
    output_size = None
    p = None

    def __init__(self, input_size, p):
        self.input_size = input_size
        self.output_size = input_size
        self.p = p

    def forwardPass(self, x, deterministic):
        if deterministic:
            return x * self.p
        else:
            return tf.nn.dropout(x, self.p)