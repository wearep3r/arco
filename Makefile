SHELL := bash
.ONESHELL:
#.SILENT:
.SHELLFLAGS := -eu -o pipefail -c
#.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables
MAKEFLAGS += --no-builtin-rules
.DEFAULT_GOAL := help

MAKEFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
APP_NAME ?= $(notdir $(patsubst %/,%,$(dir $(MAKEFILE_PATH))))

ifeq ($(origin .RECIPEPREFIX), undefined)
  $(error This Make does not support .RECIPEPREFIX. Please use GNU Make 4.0 or later)
endif
.RECIPEPREFIX = >

# Apollo
APOLLO_WHITELABEL_NAME ?= apollo
APOLLO_VERSION ?= latest

# Deprecated
IF0_ENVIRONMENT ?= ${APOLLO_WHITELABEL_NAME}
APOLLO_SPACE ?= ${IF0_ENVIRONMENT}

# Deprecated
ZERO_PROVIDER ?= generic
APOLLO_PROVIDER ?= ${ZERO_PROVIDER}

APOLLO_SPACE_DIR ?= ${HOME}/.${APOLLO_WHITELABEL_NAME}/.spaces
ENVIRONMENT_DIR ?= ${APOLLO_SPACE_DIR}

export HISTFILE="${ENVIRONMENT_DIR}/.history"
export TF_IN_AUTOMATION=1
export TF_VAR_environment=${APOLLO_SPACE}

DOCKER_SHELLFLAGS ?= run --rm -it --hostname apollo-dev -e APOLLO_DEVELOPMENT=1 -v ${HOME}/.docker:/root/.docker -v ${HOME}/.ssh:/root/.ssh -v ${HOME}/.gitconfig:/root/.gitconfig -v ${PWD}:/${APOLLO_WHITELABEL_NAME} -v ${HOME}/.${APOLLO_WHITELABEL_NAME}/:/root/.${APOLLO_WHITELABEL_NAME} ${APOLLO_WHITELABEL_NAME}:${APOLLO_VERSION}

TF_STATE_PATH=${ENVIRONMENT_DIR}/infrastructure.${APOLLO_WHITELABEL_NAME}.tfstate
TF_PLAN_PATH=${ENVIRONMENT_DIR}/infrastructure.${APOLLO_WHITELABEL_NAME}.plan

VERBOSITY ?= 0
export ANSIBLE_VERBOSITY ?= ${VERBOSITY}
export DOCKER_BUILDKIT=1
SHIPMATE_BRANCH_NAME= "$(shell git rev-parse --abbrev-ref HEAD)"
SHIPMATE_CARGO_VERSION = "${SHIPMATE_BRANCH_NAME}-$(shell git rev-parse --short HEAD)"


.PHONY: help
help:
>	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# Development
.PHONY: build
build:
> @docker image prune -f
> @docker build --pull --build-arg SHIPMATE_CARGO_VERSION="${SHIPMATE_CARGO_VERSION}" -t ${APOLLO_WHITELABEL_NAME} .

.PHONY: dev
dev: .SHELLFLAGS = ${DOCKER_SHELLFLAGS}
dev: SHELL := docker
dev:
> @enter