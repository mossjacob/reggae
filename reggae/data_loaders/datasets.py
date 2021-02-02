import torch

from scipy.integrate import odeint
import numpy as np
import pandas as pd

from reggae.data_loaders import load_barenco_puma
from reggae.data_loaders.artificial import get_artificial_dataset
from reggae.utilities import LFMDataset

from tqdm import tqdm

f64 = np.float64


class P53Data(LFMDataset):
    def __init__(self, replicate = 0):  # TODO: for now we are just considering one replicate
        m_observed, f_observed, σ2_m_pre, σ2_f_pre, t = load_barenco_puma('../data/')

        m_df, m_observed = m_observed  # (replicates, genes, times)
        self.gene_names = m_df.index
        num_times = m_observed.shape[2]
        num_genes = m_observed.shape[1]
        # f_df, f_observed = f_observed
        print(m_observed.shape)
        m_observed = torch.tensor(m_observed)[replicate].transpose(0, 1)

        self.variance = f64(σ2_m_pre)[replicate]
        # σ2_f_pre = f64(σ2_f_pre) #not used
        self.t = torch.linspace(f64(0), f64(1), 7).view(-1)

        self.data = [(self.t, m_observed)] # only one "datapoint" in this dataset

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return 1


class HafnerData(LFMDataset):
    '''
    Dataset of GSE100099
    MCF7 cells gamma-irradiated over 24 hours
    p53 is typically the protein of interest
    t=0,1,2,3,4,5,6,7,8,9,10,11,12,24
    '''
    def __init__(self, data_dir):
        target_genes = [
            'KAZN','PMAIP1','PRKAB1','CSNK1G1','E2F7','SLC30A1',
            'PTP4A1','RAP2B','SUSD6','UBR5-AS1','RNF19B','AEN','ZNF79','XPC',
            'FAM212B','SESN2','DCP1B','MDM2','GADD45A','SESN1','CDKN1A','BTG2'
        ]
        target_genes.extend([
            'DSCAM','C14orf93','RPL23AP64','RPS6KA5','MXD1', 'LINC01560', 'THNSL2',
            'EPAS1', 'ARSD', 'NACC2', 'NEDD9', 'GATS', 'ABHD4', 'BBS1', 'TXNIP',
            'KDM4A', 'ZNF767P', 'LTB4R', 'PI4K2A', 'ZNF337', 'PRKX', 'MLLT11',
            'HSPA4L', 'CROT', 'BAX', 'ORAI3', 'CES2', 'PVT1', 'ZFYVE1', 'PIK3R3',
            'TSPYL2', 'PROM2', 'ZBED5-AS1', 'CCNG1', 'STOM','IER5','STEAP3',
            'TYMSOS','TMEM198B','TIGAR','ASTN2','ANKRA2','RRM2B','TAP1','TP53I3','PNRC1',
            'GLS2','TMEM229B','IKBIP','ERCC5','KIAA1217','DDIT4','DDB2','TP53INP1'
        ])
        np.random.shuffle(target_genes)
        tfs = ['TP53']

        with open(data_dir+'/t0to24.tsv', 'r', 1) as f:
            contents = f.buffer
            df = pd.read_table(contents, sep='\t', index_col=0)

        columns = ['MCF7, t='+str(t)+' h, IR 10Gy, rep1' for t in range(13)]

        self.genes_df = df[df.index.isin(target_genes)][columns]
        self.genes_df = self.genes_df.reindex(target_genes)
        self.tfs_df = df[df.index.isin(tfs)][columns]

        m = self.genes_df.values
        genes_norm = 1/m.shape[0] * np.linalg.norm(m, axis=1, ord=None) # l2 norm
        self.genes = torch.tensor(m / np.sqrt(genes_norm.reshape(-1, 1)), dtype=torch.float32).unsqueeze(-1)

        f = self.tfs_df.values
        tfs_norm = 1/f.shape[0] * np.linalg.norm(f, axis=1, ord=None) # l2 norm
        self.tfs = f / np.sqrt(tfs_norm.reshape(-1, 1))

        self.t = torch.tensor([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], dtype=torch.float32).view(-1, 1)
        self.t = self.t.repeat([self.genes.shape[0], 1, 1])
        self.data = list(zip(self.t, self.genes))

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return self.genes.shape[0]


class ArtificialData(LFMDataset):
    def __init__(self, delay=False):
        nodelay_dataset, delay_dataset = get_artificial_dataset()
        p_nodelay, m_nodelay = nodelay_dataset
        replicate = 0
        m_nodelay = m_nodelay[replicate]
        p_nodelay = p_nodelay[replicate]
        self.num_genes = m_nodelay.shape[0]
        self.num_tfs = p_nodelay.shape[0]
        self.f_observed = p_nodelay
        num_times = m_nodelay.shape[1]

        self.gene_names = np.arange(self.num_genes)
        m_observed = torch.tensor(m_nodelay).transpose(0, 1)

        self.t = torch.linspace(f64(0), f64(1), num_times, dtype=torch.float64).reshape((-1, 1))
        self.data = [(self.t, m_observed)]  # only one "datapoint" in this dataset

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return 1


class MarkovJumpProcess:
    """
    Implements a generic markov jump process and algorithms for simulating it.
    It is an abstract class, it needs to be inherited by a concrete implementation.
    """

    def __init__(self, init, params):

        self.state = np.asarray(init)
        self.params = np.asarray(params)
        self.time = 0.0

    def _calc_propensities(self):
        raise NotImplementedError('This is an abstract method and should be implemented in a subclass.')

    def _do_reaction(self, reaction):
        raise NotImplementedError('This is an abstract method and should be implemented in a subclass.')

    def sim_steps(self, num_steps):
        """Simulates the process with the gillespie algorithm for a specified number of steps."""

        times = [self.time]
        states = [self.state.copy()]

        for _ in range(num_steps):

            rates = self.params * self._calc_propensities()
            total_rate = rates.sum()

            if total_rate == 0:
                self.time = float('inf')
                break

            self.time += np.random.exponential(scale=1 / total_rate)

            reaction = self.discrete_sample(rates / total_rate)[0]
            self._do_reaction(reaction)

            times.append(self.time)
            states.append(self.state.copy())

        return times, np.array(states)

    def sim_time(self, dt, duration, max_n_steps=float('inf')):
        """Simulates the process with the gillespie algorithm for a specified time duration."""

        num_rec = int(duration / dt) + 1
        states = np.zeros([num_rec, self.state.size])
        cur_time = self.time
        n_steps = 0

        for i in range(num_rec):

            while cur_time > self.time:

                rates = self.params * self._calc_propensities()
                total_rate = rates.sum()

                if total_rate == 0:
                    self.time = float('inf')
                    break

                exp_scale = max(1 / total_rate, 1e-3)
                self.time += np.random.exponential(scale=exp_scale)

                reaction = np.random.multinomial(1, rates / total_rate)
                reaction = np.argmax(reaction)
                self._do_reaction(reaction)

                n_steps += 1
                if n_steps > max_n_steps:
                    raise SimTooLongException(max_n_steps)

            states[i] = self.state.copy()
            cur_time += dt

        return np.array(states)


class LotkaVolterra(MarkovJumpProcess):
    """Implements the lotka-volterra population model."""

    def _calc_propensities(self):

        x, y = self.state
        xy = x * y
        return np.array([xy, x, y, xy])

    def _do_reaction(self, reaction):

        if reaction == 0:
            self.state[0] += 1
        elif reaction == 1:
            self.state[0] -= 1
        elif reaction == 2:
            self.state[1] += 1
        elif reaction == 3:
            self.state[1] -= 1
        else:
            raise ValueError('Unknown reaction.')


class StochasticLotkaVolteraData(LFMDataset):
    """
    Dataset of time-seires sampled from a Lotka-Voltera model
    ----------
    amplitude_range : tuple of float
        Defines the range from which the amplitude (i.e. a) of the sine function
        is sampled.
    shift_range : tuple of float
        Defines the range from which the shift (i.e. b) of the sine function is
        sampled.
    num_samples : int
        Number of samples of the function contained in dataset.
    num_points : int
        Number of points at which to evaluate f(x) for x in [-pi, pi].
    """

    def __init__(self, initial_X=50, initial_Y=100,
                 num_samples=1000, dt=0.2):
        self.initial_X = initial_X
        self.initial_Y = initial_Y
        self.num_samples = num_samples
        self.x_dim = 1
        self.y_dim = 2
        self.dt = dt

        self.init = [self.initial_X, self.initial_Y]
        self.params = [0.01, 0.5, 1.0, 0.01]
        self.duration = 30

        # Generate data
        self.data = []
        print("Creating dataset...", flush=True)

        removed = 0
        for samples in range(num_samples):
            lv = LotkaVolterra(self.init, self.params)
            states = lv.sim_time(dt, self.duration)
            times = torch.linspace(0.0, self.duration,
                                   int(self.duration / dt) + 1)
            times = times.unsqueeze(1)

            # Ignore outlier populations
            if np.max(states) > 600:
                removed += 1
                continue

            # Scale the population ranges to be closer to the real model
            states = torch.FloatTensor(states) * 1 / 100
            times = times * 1 / 20
            self.data.append((times, states))

        self.num_samples -= removed

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return self.num_samples


class DeterministicLotkaVolteraData(LFMDataset):
    """
    Dataset of Lotka-Voltera time series.
      Populations (u,v) evolve according to
        u' = \alpha u - \beta u v
        v' = \delta uv - \gamma v
      with the dataset sampled either with (u_0, v_0) fixed and (\alpha, \beta,
      \gamma, \delta) varied, or varying the initial populations for a fixed set
      of greeks.
    If initial values for (u,v) are provided then the greeks are sampled from
        (0.9,0.05,1.25,0.5) to (1.1,0.15,1.75,1.0)
    if values are provided for the greeks then (u_0 = v_0) is sampled from
        (0.5) to (2.0)
    if both are provided, defaults to initial population mode (greeks vary)
    ----------
    initial_u	: int
        fixed initial value for u
    initial_v	: int
        fixed initial value for v
    fixed_alpha : int
        fixed initial value for \alpha
    fixed_beta	: int
        fixed initial value for \beta
    fixed_gamma : int
        fixed initial value for \gamme
    fixed_delta : int
        fixed initial value for \delta
    end_time : float
        the final time (simulation runs from 0 to end_time)
    steps : int
        how many time steps to take from 0 to end_time
    num_samples : int
        Number of samples of the function contained in dataset.
    """

    def __init__(self, initial_u=None, initial_v=None,
                 alpha=None, beta=None, gamma=None, delta=None,
                 num_samples=1000, steps=150, end_time=15):

        if initial_u is None:
            self.mode = 'greek'
            self.alpha = alpha
            self.beta = beta
            self.gamma = gamma
            self.delta = delta
        else:
            self.mode = 'population'
            self.initial_u = initial_u
            self.initial_v = initial_v

        print('Lotka-Voltera is in {self.mode} mode.')

        self.num_samples = num_samples
        self.steps = steps
        self.end_time = end_time

        # Generate data
        self.data = []
        print("Creating dataset...", flush=True)

        removed = 0
        for samples in tqdm(range(num_samples)):
            times, states = self.generate_ts()
            #  normalise times
            times = torch.FloatTensor(times) / 10
            times = times.unsqueeze(1)

            states = torch.FloatTensor(states)
            if self.mode == 'population':
                states = states / 100
            # states = torch.cat((states, times), dim=-1)

            self.data.append((times, states))

        self.num_samples -= removed

    def generate_ts(self):
        if self.mode == 'population':
            X_0 = np.array([self.initial_u, self.initial_v])
            a = np.random.uniform(0.9, 1.1)
            b = np.random.uniform(0.05, 0.15)
            c = np.random.uniform(1.25, 1.75)
            d = np.random.uniform(0.5, 1.0)
        else:
            equal_pop = np.random.uniform(0.25, 1.)
            X_0 = np.array([2 * equal_pop, equal_pop])
            a, b, c, d = self.alpha, self.beta, self.gamma, self.delta

        def dX_dt(X, t=0):
            """ Return the growth rate of fox and rabbit populations. """
            return np.array([a * X[0] - b * X[0] * X[1],
                             -c * X[1] + d * X[0] * X[1]])

        t = np.linspace(0, self.end_time, self.steps)
        X = odeint(dX_dt, X_0, t)

        return t, X

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return self.num_samples
