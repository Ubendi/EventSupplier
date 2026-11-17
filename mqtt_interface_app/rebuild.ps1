docker build -t mqtt_interface_app .
docker rm -f mqtt_interface_app
docker run -d `
    --name mqtt_interface_app `
    --restart=always `
    --env-file .\env\laptop.env `
    -p 8081:8081 `
    -v ${PWD}/data:/app/data `
    mqtt_interface_app
