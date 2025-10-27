from gradio_client import Client

client = Client("http://127.0.0.1:7860/")
result = client.predict(
	title="Hello!!",
	offering="Hello!!",
	api_name="/begin"
)
print(result)
# client = Client("http://127.0.0.1:7860/")
result = client.predict(
	player_text="Hello!!",
	api_name="/advance"
)
print(result)