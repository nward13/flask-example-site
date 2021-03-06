SHELL := /bin/bash

NAME = sample

dump-schema:
	docker exec $(NAME)_db_1 /bin/bash -c 'mysql -u root -p"$$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS db_0; CREATE DATABASE db_0;"'
	docker exec $(NAME)_db_1 /bin/bash -c 'mysql -u root -p"$$MYSQL_ROOT_PASSWORD" -v -e "GRANT ALL PRIVILEGES ON db_0.* TO web_user@\"%\";"'
	docker exec $(NAME)_web_1 /bin/bash -c 'flask initdb --uri="mysql://$$MYSQL_USER:$$MYSQL_PASSWORD@db:3306/db_0"'
	docker exec $(NAME)_db_1 /bin/bash -c 'mysqldump -u root -p"$$MYSQL_ROOT_PASSWORD" --no-data db_0' > sample/schema.sql

shell:
	docker exec -it $(NAME)_$(word 2, $(MAKECMDGOALS) )_1 /bin/bash

restart:
	docker restart $(NAME)_$(word 2, $(MAKECMDGOALS) )_1

build:
	docker build -t sample/sample:latest sample

down:
	docker-compose -f sample.yml -p $(NAME) down

up:
	docker-compose -f sample.yml -p $(NAME) up
