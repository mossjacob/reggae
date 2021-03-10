import tensorflow_probability as tfp
import tensorflow as tf


class HMCSampler(tfp.mcmc.NoUTurnSampler):

    def __init__(self, likelihood_fn, params_list, step_size):
        self.likelihood_fn = likelihood_fn
        self.params_list = params_list
        self.transforms = [param.transform for param in params_list]
        super().__init__(self.log_prob, step_size)

    def log_prob(self, *args):
        print(*args)
        new_prob = 0

        param_kwargs = {}
        for i, param in enumerate(self.params_list):
            val = self.transforms[i](args[i])

            # Prepare likelihood params
            param_kwargs[param.name] = val

            # Add prior:
            new_prob += tf.reduce_sum(param.prior[i].log_prob(val))

        # Add likelihood:
        new_prob += tf.reduce_sum(self.likelihood_fn(**param_kwargs))
        return new_prob