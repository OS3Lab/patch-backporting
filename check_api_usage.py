import datetime
import requests
from dotenv import load_dotenv
import os

load_dotenv()

price = {
    'gpt-4-turbo':(0.01, 0.03),
    'gpt-4-turbo-2024-04-09':(0.01, 0.03),
    'gpt-4-0125-preview':(0.01, 0.03),
    'gpt-4o-2024-05-13':(0.005 , 0.015),
}

def get_usage(api_key):

    headers = {
        # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.99 Safari/537.36',
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json"
    }


    # Get recent usage info
    start_date = (datetime.datetime.now() - datetime.timedelta(days=99)).strftime("%Y-%m-%d")
    end_date = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    data = (datetime.datetime.now()).strftime("%Y-%m-%d")
    resp_billing = requests.get(f"https://api.openai.com/v1/usage?date={data}", headers=headers)
    if not resp_billing.ok:
        return resp_billing.text
    
    billing_data = resp_billing.json()
    total = 0.0
    for item in billing_data['data']:
        if item['snapshot_id'] in price:
            input_p , output_p = price[item['snapshot_id']]
            total += item['n_context_tokens_total'] * input_p/1000
            total += item['n_generated_tokens_total'] * output_p/1000
        else:
            print(f"Unknown model: {item['snapshot_id']}")

    print(f"Total cost: ${total:.2f}")
    return total
                

if __name__ == '__main__':
    
    print(get_usage(os.getenv("OPENAI_API_KEY")))