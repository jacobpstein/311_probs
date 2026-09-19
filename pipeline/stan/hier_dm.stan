// Two-level hierarchical Dirichlet-Multinomial for one borough and one complaint type.
// Merging categories of a Dirichlet gives a Dirichlet with the parameters summed, so the
// hierarchy can be fitted on merged categories (here: within 24h / later) without changing it:
//   p_nta[a] ~ Dirichlet(k2 * m_b)                 (neighborhoods around the borough mean)
//   y[g]     ~ DirichletMultinomial(k3 * p_nta[a]) (tract counts; tract distribution integrated out)
// with log-normal priors on both concentrations. Unlike the production cascade nothing is
// plugged in: the neighborhood distributions and both concentrations are sampled, so the
// tract posteriors carry all of their uncertainty.
data {
  int<lower=2> K;
  int<lower=1, upper=K - 1> n_first;      // the first n_first categories count as "resolved within 24h"
  int<lower=1> A;
  int<lower=1> G;
  array[G] int<lower=1, upper=A> nta;
  array[G, K] int<lower=0> y;
  vector<lower=0>[K] m_b;                 // borough mean, fixed
  real mu_log_k2;
  real<lower=0> sd_log_k2;
  real mu_log_k3;
  real<lower=0> sd_log_k3;
}
transformed data {
  array[G] int N;
  for (g in 1:G) N[g] = sum(y[g]);
}
parameters {
  real log_k2;
  real log_k3;
  array[A] simplex[K] p_nta;
}
transformed parameters {
  real<lower=0> k2 = exp(log_k2);
  real<lower=0> k3 = exp(log_k3);
}
model {
  log_k2 ~ normal(mu_log_k2, sd_log_k2);
  log_k3 ~ normal(mu_log_k3, sd_log_k3);
  for (a in 1:A) p_nta[a] ~ dirichlet(k2 * m_b);
  for (g in 1:G) {
    if (N[g] > 0) y[g] ~ dirichlet_multinomial(k3 * p_nta[nta[g]]);
  }
}
generated quantities {
  // posterior of each tract's true P(resolved within 24h), and its conditional mean
  array[G] real cum24;
  array[G] real mean24;
  for (g in 1:G) {
    vector[K] a = k3 * p_nta[nta[g]] + to_vector(y[g]);
    vector[K] pg = dirichlet_rng(a);
    cum24[g] = sum(pg[1:n_first]);
    mean24[g] = sum(a[1:n_first]) / sum(a);
  }
}
