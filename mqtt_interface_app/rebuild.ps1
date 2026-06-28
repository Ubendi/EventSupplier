docker build -t mqtt_interface_app .
docker rm -f mqtt_interface_app
docker run -d `
    --name mqtt_interface_app `
    --restart=always `
    --env-file .\env\laptop.env `
    -v ${PWD}/data/positions.json:/app/vlc_interface/positions.json `
    mqtt_interface_app
