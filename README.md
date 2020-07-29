# update manager
update manager update local docker images by pulling the latest docker images from ECR or from latest install package file

## setup lucidum folder 
> cp resources/docker-compose_file ../docker-compose.yml
> cp resources/env_file ../.env
> mkdir -p ../mongo/db
> chmod -R 777 ../mongo
> mkdir -p ../mysql/config
> mkdir -p ../mysql/db
> chmod -R 777 ../mysql
> mkdir -p ../web/app/hostdata
> mkdir -p ../web/app/logs
> chmod -R 777 ../web

> sudo mkdir -p /usr/lucidum_backup
> sudo chown -R demo:demo /usr/lucidum_backup
> sudo chmod -R 777 /usr/lucidum_backup


## update from ECR

