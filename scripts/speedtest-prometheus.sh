#!/bin/bash

PUSHGATEWAY="http://localhost:9091"
JOB="speedtest"

# Roda o speedtest
RESULT=$(speedtest-ookla --accept-license --accept-gdpr --format=json 2>/dev/null)

if [ -z "$RESULT" ]; then
    echo "Speedtest falhou"
    exit 1
fi

DOWNLOAD=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['download']['bandwidth']*8)")
UPLOAD=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['upload']['bandwidth']*8)")
PING=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['ping']['latency'])")
JITTER=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['ping']['jitter'])")
SERVER=$(echo $RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['server']['name'])")

echo "Download: $DOWNLOAD bps | Upload: $UPLOAD bps | Ping: $PING ms | Jitter: $JITTER ms | Servidor: $SERVER"

# Envia pro Pushgateway
cat <<EOF | curl -s --data-binary @- "$PUSHGATEWAY/metrics/job/$JOB"
# HELP speedtest_download_bps Download speed in bits per second
# TYPE speedtest_download_bps gauge
speedtest_download_bps $DOWNLOAD
# HELP speedtest_upload_bps Upload speed in bits per second
# TYPE speedtest_upload_bps gauge
speedtest_upload_bps $UPLOAD
# HELP speedtest_ping_ms Ping latency in milliseconds
# TYPE speedtest_ping_ms gauge
speedtest_ping_ms $PING
# HELP speedtest_jitter_ms Jitter in milliseconds
# TYPE speedtest_jitter_ms gauge
speedtest_jitter_ms $JITTER
EOF

echo "Métricas enviadas pro Prometheus"
