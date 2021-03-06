import tensorflow as tf
from layers.convolution import shufflenet_unit, conv2d, max_pool_2d
from utils.misc import load_obj, _debug, save_obj
import os


class ShuffleNet:
    """ShuffleNet is implemented here!"""

    # MEAN = [103.94, 116.78, 123.68]
    MEAN = [73.29132098, 83.04442645, 72.5238962]

    # NORMALIZER = 0.017

    def __init__(self, x_input, num_classes, pretrained_path, train_flag, batchnorm_enabled=True, num_groups=3,
                 weight_decay=4e-5,
                 bias=0.0):
        self.x_input = x_input
        self.train_flag = train_flag
        self.num_classes = num_classes
        self.num_groups = num_groups
        self.bias = bias
        self.wd = weight_decay
        self.batchnorm_enabled = batchnorm_enabled
        self.pretrained_path = os.path.realpath(os.getcwd()) + "/" + pretrained_path
        self.score_fr = None
        self.stage2 = None
        self.stage3 = None
        self.stage4 = None
        self.max_pool = None
        self.conv1 = None

        # These feed layers are for the decoder
        self.feed1 = None
        self.feed2 = None

        # A number stands for the num_groups
        # Output channels for conv1 layer
        self.output_channels = {'1': [144, 288, 576], '2': [200, 400, 800], '3': [240, 480, 960], '4': [272, 544, 1088],
                                '8': [384, 768, 1536], 'conv1': 24}

    def stage(self, x, stage=2, repeat=3, dilation=1):
        if 2 <= stage <= 4:
            if dilation > 1:
                stage_layer = shufflenet_unit('stage' + str(stage) + '_0', x=x, w=None,
                                              num_groups=self.num_groups,
                                              group_conv_bottleneck=not (stage == 2),
                                              num_filters=
                                              self.output_channels[str(self.num_groups)][
                                                  stage - 2],
                                              stride=(1, 1), dilation=dilation,
                                              fusion='concat', l2_strength=self.wd,
                                              bias=self.bias,
                                              batchnorm_enabled=self.batchnorm_enabled,
                                              is_training=self.train_flag)
            else:
                stage_layer = shufflenet_unit('stage' + str(stage) + '_0', x=x, w=None,
                                              num_groups=self.num_groups,
                                              group_conv_bottleneck=not (stage == 2),
                                              num_filters=
                                              self.output_channels[str(self.num_groups)][
                                                  stage - 2],
                                              stride=(2, 2),
                                              fusion='concat', l2_strength=self.wd,
                                              bias=self.bias,
                                              batchnorm_enabled=self.batchnorm_enabled,
                                              is_training=self.train_flag)
            for i in range(1, repeat + 1):
                stage_layer = shufflenet_unit('stage' + str(stage) + '_' + str(i),
                                              x=stage_layer, w=None,
                                              num_groups=self.num_groups,
                                              group_conv_bottleneck=True,
                                              num_filters=self.output_channels[
                                                  str(self.num_groups)][stage - 2],
                                              stride=(1, 1),
                                              fusion='add',
                                              l2_strength=self.wd,
                                              bias=self.bias,
                                              batchnorm_enabled=self.batchnorm_enabled,
                                              is_training=self.train_flag)
            return stage_layer
        else:
            raise ValueError("Stage should be from 2 -> 4")

    def build(self):
        print("Building the ShuffleNet..")
        with tf.variable_scope('shufflenet_encoder'):
            with tf.name_scope('Pre_Processing'):
                red, green, blue = tf.split(self.x_input, num_or_size_splits=3, axis=3)
                preprocessed_input = tf.concat([
                    tf.subtract(blue, ShuffleNet.MEAN[0]) / tf.constant(255.0),
                    tf.subtract(green, ShuffleNet.MEAN[1]) / tf.constant(255.0),
                    tf.subtract(red, ShuffleNet.MEAN[2]) / tf.constant(255.0),
                ], 3)
            self.conv1 = conv2d('conv1', x=preprocessed_input, w=None, num_filters=self.output_channels['conv1'],
                                kernel_size=(3, 3),
                                stride=(2, 2), l2_strength=self.wd, bias=self.bias,
                                batchnorm_enabled=self.batchnorm_enabled, is_training=self.train_flag,
                                activation=tf.nn.relu, padding='VALID')
            _debug(self.conv1)
            padded = tf.pad(self.conv1, [[0, 0], [0, 1], [0, 1], [0, 0]], "CONSTANT")
            self.max_pool = max_pool_2d(padded, size=(3, 3), stride=(2, 2), name='max_pool')
            _debug(self.max_pool)
            self.stage2 = self.stage(self.max_pool, stage=2, repeat=3)
            _debug(self.stage2)
            self.stage3 = self.stage(self.stage2, stage=3, repeat=7)
            _debug(self.stage3)
            self.stage4 = self.stage(self.stage3, stage=4, repeat=3)
            _debug(self.stage4)

            self.feed1 = self.stage3
            self.feed2 = self.stage2

            # First Experiment is to use the regular conv2d
            self.score_fr = conv2d('conv_1c_1x1', self.stage4, num_filters=self.num_classes, l2_strength=self.wd,
                                   kernel_size=(1, 1))

            print("\nEncoder ShuffleNet is built successfully\n\n")

    def __save(self, sess):
        file_name= self.pretrained_path
        variables = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)
        try:
            print("Loading ImageNet pretrained weights...")
            dict = load_obj(file_name)
            saved_dict= {}
            run_list = []
            for variable in variables:
                for key, value in dict.items():
                    if key + ":" in variable.name:
                        saved_dict[key]= sess.run(variable)

            save_obj(saved_dict, 'pretrained_weights/shufflenet_cityscapes.pkl')
            for k, v in saved_dict.items():
                if k not in dict.keys():
                    import pdb; pdb.set_trace()

            print("ImageNet Pretrained Weights Loaded Initially\n\n")
        except KeyboardInterrupt:
            print("No pretrained ImageNet weights exist. Skipping...\n\n")


    def __restore(self, file_name, sess):
        variables = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES)
        try:
            print("Loading ImageNet pretrained weights...")
            dict = load_obj(file_name)
            run_list = []
            for variable in variables:
                for key, value in dict.items():
                    # Adding ':' means that we are interested in the variable itself and not the variable parameters
                    # that are used in adaptive optimizers
                    if key + ":" in variable.name:
                        run_list.append(tf.assign(variable, value))

            sess.run(run_list)
            print("ImageNet Pretrained Weights Loaded Initially\n\n")
        except KeyboardInterrupt:
            print("No pretrained ImageNet weights exist. Skipping...\n\n")

    def load_pretrained_weights(self, sess):
        self.__restore(self.pretrained_path, sess)
        #self.__save(sess)
