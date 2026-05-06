import faust

# Création de l’application Faust
app = faust.App(
    'earthquake-stream',
    broker='kafka://localhost:9092',
    value_serializer='json',
    web_port=6066,
    web_cors_origins=['*']
)

latest_quakes = []