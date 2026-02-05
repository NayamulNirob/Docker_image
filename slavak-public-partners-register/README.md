See running containers
docker ps

docker build --no-cache -t slovok-register .

docker run `
  -v ${PWD}/outputfile:/app/outputfile `
  -v ${PWD}/cache:/app/cache `
  slovok-register

Stop the running container

Use the CONTAINER ID (or name):

docker stop a1b2c3d4e5f6
