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

#DOCKER_SHELLFLAGS ?= run --rm -it --hostname arco-dev -v ${HOME}/.docker:/root/.docker -v ${HOME}/.ssh:/root/.ssh -v ${HOME}/.gitconfig:/root/.gitconfig -v ${PWD}:/${APOLLO_WHITELABEL_NAME} -v ${HOME}/.${APOLLO_WHITELABEL_NAME}/:/root/.${APOLLO_WHITELABEL_NAME} ${APOLLO_WHITELABEL_NAME}:${APOLLO_VERSION}

.PHONY: help
help:
>	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: build-package
build-package:
> poetry build

.PHONY: build-docker
build-docker:
> docker build --build-arg BUILD_DATE=${ARCO_DATE} --build-arg BUILD_VERSION=$(shell arco --version) --build-arg VCS_REF=${CI_COMMIT_SHORT_SHA} -t ${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME} .

.PHONY: publish-docker
publish-docker: build-docker
> docker tag ${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME} ${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME}:$(shell arco --version)
> docker push ${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME}:$(shell arco --version)
> docker tag ${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME} ${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME}:latest
> docker push ${CI_PROJECT_NAMESPACE}/${CI_PROJECT_NAME}:latest

.PHONY: publish-semrel
publish-sem-rel:
#> git push origin master
> semantic-release publish

.PHONY: publish
publish: publish-semrel publish-docker
#> @docker image prune -f
> echo "Publishing"

.PHONY: dev
dev: .SHELLFLAGS = ${DOCKER_SHELLFLAGS}
dev: SHELL := docker
dev:
> @dev