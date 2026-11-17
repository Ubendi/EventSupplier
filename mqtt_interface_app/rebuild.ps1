param(
    # env/laptop.env on the laptop, env/pc.env on the PC (default)
    [string]$EnvFile = "pc.env"
)

docker build -t mqtt_interface_app .
docker rm -f mqtt_interface_app
docker run -d `
    --name mqtt_interface_app `
    --restart=always `
    --env-file ".\env\$EnvFile" `
    -p 8081:8081 `
    -v ${PWD}/data:/app/data `
    mqtt_interface_app
