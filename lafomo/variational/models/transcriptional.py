
import torch
from torch.nn.parameter import Parameter
from torch.distributions.normal import Normal

from lafomo.variational.models import OrdinaryLFM
from lafomo.configuration import VariationalConfiguration
from lafomo.utilities.torch import softplus
from lafomo.datasets import LFMDataset

class TranscriptionalRegulationLFM(OrdinaryLFM):
    def __init__(self, gp_model, config: VariationalConfiguration, dataset):
        super().__init__(gp_model, config, dataset)
        self.decay_rate = Parameter(0.1 + torch.rand(torch.Size([self.num_outputs, 1]), dtype=torch.float64))
        self.basal_rate = Parameter(torch.rand(torch.Size([self.num_outputs, 1]), dtype=torch.float64))
        self.sensitivity = Parameter(0.2 + torch.rand(torch.Size([self.num_outputs, 1]), dtype=torch.float64))

    def initial_state(self):
        return self.basal_rate / self.decay_rate

    def odefunc(self, t, h):
        """h is of shape (num_samples, num_outputs, 1)"""
        self.nfe += 1
        # if (self.nfe % 100) == 0:
        #     print(t)

        decay = self.decay_rate * h

        f = self.f[:, :, self.t_index].unsqueeze(2)

        h = self.basal_rate + self.sensitivity * f - decay
        if t > self.last_t:
            self.t_index += 1
        self.last_t = t
        return h


class SingleLinearLFM(TranscriptionalRegulationLFM):

    def G(self, f):
        # I = 1 so just repeat for num_outputs
        return f.repeat(1, self.num_outputs, 1)


class NonLinearLFM(TranscriptionalRegulationLFM):

    def G(self, f):
        # I = 1 so just repeat for num_outputs
        return softplus(f).repeat(1, self.num_outputs, 1)

    def predict_f(self, t_predict):
        # Sample from the latent distribution
        q_f = self.get_latents(t_predict)
        f = q_f.sample([500])  # (S, I, t)
        # This is a hack to wrap the latent function with the nonlinearity. Note we use the same variance.
        f = torch.mean(self.G(f), dim=0)[0]
        return torch.distributions.multivariate_normal.MultivariateNormal(f, scale_tril=q_f.scale_tril)


class ExponentialLFM(NonLinearLFM):

    def G(self, f):
        # I = 1 so just repeat for num_outputs
        return torch.exp(f).repeat(1, self.num_outputs, 1)


class MultiLFM(TranscriptionalRegulationLFM):
    def __init__(self, num_latents, config, kernel, t_inducing, dataset):
        super().__init__(num_latents, config, kernel, t_inducing, dataset)
        self.w = Parameter(torch.ones((self.num_outputs, self.num_latents), dtype=torch.float64))
        self.w_0 = Parameter(torch.ones((self.num_outputs, 1), dtype=torch.float64))

    def G(self, f):
        p_pos = softplus(f)  # (S, I, extras)
        interactions = torch.matmul(self.w, torch.log(p_pos+1e-50)) + self.w_0  # (J,I)(I,e)+(J,1)
        return torch.sigmoid(interactions)  # TF Activation Function (sigmoid)

    def predict_f(self, t_predict):
        q_f = self.get_latents(t_predict.reshape(-1))
        f = softplus(q_f.sample([500]))
        return torch.distributions.multivariate_normal.MultivariateNormal(f, scale_tril=q_f.scale_tril)


class PoissonLFM(TranscriptionalRegulationLFM):
    def __init__(self, num_latents, config, kernel, t_inducing, dataset: LFMDataset):
        super().__init__(num_latents, config, kernel, t_inducing, dataset)

    """Adds poison to the latent forces"""
    def G(self, λ):
        # λ (I, points) is the parameter of the poison distribution
        print('lam shape', λ.shape)
        # f = Poisson(λ).rsample() #  not implemented - no reparam trick for Poisson implemented
        # so we use an approximation as a N(λ, λ)
        f = Normal(λ, λ).rsample()
        return f.repeat(self.num_outputs, 1)
