docker build -t mqtt_interface_app .
docker rm -f mqtt_interface_app
docker run -d `
    --name mqtt_interface_app `
    --restart=always `
    -e VLC_HOST=http://host.docker.internal `
    -e VLC_PORT=8080 `
    -e VLC_KEY=F8006B8645 `
    -v ${PWD}/data/positions.json:/app/vlc_interface/positions.json `
    mqtt_interface_app
