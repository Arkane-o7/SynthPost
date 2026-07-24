from sarvamai import SarvamAI

client = SarvamAI(
    api_subscription_key="sk_92w1h5a0_BijEtkEZPQZsxh1g7bdYlaNc"
)

response = client.chat.completions(
    model="sarvam-105b",
    messages=[
        {"role": "user", "content": "What is the capital of India?"}
    ]
)

print(response.choices[0].message.content)