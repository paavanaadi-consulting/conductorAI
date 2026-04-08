import anthropic

client = anthropic.Anthropic(api_key="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")

prompt = "Give 5 PySpark interview questions with answers."

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=300,
    messages=[{"role": "user", "content": prompt}]
)

print(response.content[0].text)