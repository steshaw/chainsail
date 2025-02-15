#!/usr/bin/env bash

SCHEDULER_URL=$(minikube service scheduler --url)
MCMC_STATS_SERVER_URL=$(minikube service mcmc-stats-server --url)
GRAPHITE_URL=$(minikube service graphite --url | head -n1)

export SCHEDULER_URL=$SCHEDULER_URL
export GRAPHITE_URL=$GRAPHITE_URL
export MCMC_STATS_URL=$MCMC_STATS_SERVER_URL
yarn run dev
