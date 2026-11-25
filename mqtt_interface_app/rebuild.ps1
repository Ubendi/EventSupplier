param(
    # env/laptop.env on the laptop, env/pc.env on the PC (default)
    [string]$EnvFile = "pc.env",
    # Host folder that holds the media, mounted into the container at /media.
    # Also set media_root=/media and media_host_path=<this folder> in the web
    # UI Settings tab so opened files map to host paths VLC can read.
    [string]$MediaDir = ""
)

docker build -t mqtt_interface_app .
docker rm -f mqtt_interface_app

$extraArgs = @()
if ($MediaDir -ne "") {
    $extraArgs += "-v"
    $extraArgs += "$($MediaDir):/media"
}

docker run -d `
    --name mqtt_interface_app `
    --restart=always `
    --env-file ".\env\$EnvFile" `
    -p 8081:8081 `
    -v ${PWD}/data:/app/data `
    @extraArgs `
    mqtt_interface_app
