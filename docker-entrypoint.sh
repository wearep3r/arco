#!/bin/bash
set -e

if [ "$CI" = "1" ];
then
  # in CI
  export SHELL ["/bin/bash", "-c"]
fi

if [ "$1" = 'dev' ];
then
  cd /code
  exec "/bin/bash"
elif [ "$1" = 'arco' ];
then
  exec "$@"
else
  set -- arco "$@"
  cd /code
fi

exec "$@"