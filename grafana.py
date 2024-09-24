import json 

import boto3 

import requests 

import os 

import re 

from urllib.parse import unquote_plus 

 

grafana_base_url = 'http://3.109.56.223:3000' 

s3_client = boto3.client('s3') 

secrets_client = boto3.client('secretsmanager', region_name='ap-south-1') 

 

def get_secret(secret_name): 

    try: 

        get_secret_value_response = secrets_client.get_secret_value(SecretId=secret_name) 

        secret = get_secret_value_response['SecretString'] 

        return json.loads(secret) 

    except Exception as e: 

        print(f"Error retrieving secret: {str(e)}") 

        raise e 

 

def get_grafana_folders(grafana_base_url, grafana_api_key): 

    headers = { 

        'Content-Type': 'application/json', 

        'Authorization': f'Bearer {grafana_api_key}' 

    } 

     

    url = f"{grafana_base_url}/api/folders" 

    response = requests.get(url, headers=headers) 

    response.raise_for_status() 

     

    folders = response.json() 

    return folders 

 

def get_folder_id(folders, folder_title): 

    for folder in folders: 

        if folder['title'] == folder_title: 

            return folder['id'] 

    return None 

 

def create_folder(grafana_base_url, grafana_api_key, folder_title): 

    headers = { 

        'Content-Type': 'application/json', 

        'Authorization': f'Bearer {grafana_api_key}' 

    } 

     

    payload = { 

        'title': folder_title 

    } 

     

    url = f"{grafana_base_url}/api/folders" 

    response = requests.post(url, headers=headers, json=payload) 

    response.raise_for_status() 

     

    folder = response.json() 

    return folder 

 

def extract_year_from_title(title): 

    match = re.search(r'\b(20\d{2})\b', title) 

    return match.group(1) if match else None 

 

def lambda_handler(event, context): 

    try: 

        bucket = event['Records'][0]['s3']['bucket']['name'] 

        key = event['Records'][0]['s3']['object']['key'] 

        key = unquote_plus(key) 

        print(bucket) 

        print(key) 

        print(event) 

 

        # Extract the file name from the key 

        file_name = os.path.basename(key) 

        dashboard_title = os.path.splitext(file_name)[0] 

        print("Dashboard Title:", dashboard_title) 

 

        # Construct the URL of the file in S3 

        s3_url = f'https://{bucket}.s3.amazonaws.com/{key}' 

        print("S3 URL:", s3_url) 

 

        # Retrieve Grafana API key from Secrets Manager 

        secret_name = 'grafana/api' 

        secrets = get_secret(secret_name) 

        print("Secrets:", secrets) 

 

        grafana_api_key = secrets.get('grafana-api-key') 

 

        if not grafana_api_key: 

            raise KeyError("grafana-api-key not found in secrets") 

 

        grafana_url = f'{grafana_base_url}/api/dashboards/uid/c5b181b2-38c4-4e1e-bde5-abdda68f2642' 

        headers = { 

            'Content-Type': 'application/json', 

            'Authorization': f'Bearer {grafana_api_key}', 

        } 

 

        response = requests.get(grafana_url, headers=headers) 

        print(response) 

 

        if response.status_code != 200: 

            print('Error:', response.content) 

            return { 

                'statusCode': response.status_code, 

                'body': json.dumps({'error': response.content.decode('utf-8')}) 

            } 

 

        dashboard = json.loads(response.content) 

        print(dashboard) 

 

        # Update the title of the dashboard to indicate it is a copy 

        dashboard['dashboard']['title'] = dashboard_title 

        # Remove the UID to ensure Grafana assigns a new one 

        dashboard['dashboard'].pop('uid', None) 

        dashboard['dashboard'].pop('id', None) 

 

        # Extract the year from the dashboard title 

        year = extract_year_from_title(dashboard_title) 

        if not year: 

            raise ValueError("Year not found in dashboard title") 

 

        folder_title = f'Fin-ops-{year}' 

        folders = get_grafana_folders(grafana_base_url, grafana_api_key) 

        folder_id = get_folder_id(folders, folder_title) 

 

        if not folder_id: 

            new_folder = create_folder(grafana_base_url, grafana_api_key, folder_title) 

            folder_id = new_folder['id'] 

            print("Created new folder:", new_folder) 

        else: 

            print("Folder already exists:", folder_title) 

 

        # Create a new dashboard by saving the copy in the specified folder 

        payload = { 

            'dashboard': dashboard['dashboard'], 

            'folderId': folder_id, 

            'overwrite': False 

        } 

 

        response_copy = requests.post(f'{grafana_base_url}/api/dashboards/db', headers=headers, json=payload) 

        print("Response Copy:", response_copy) 

 

        if response_copy.status_code != 200: 

            print('Error:', response_copy.content) 

            return { 

                'statusCode': response_copy.status_code, 

                'body': json.dumps({'error': response_copy.content.decode('utf-8')}) 

            } 

 

        new_dashboard = response_copy.json() 

        new_dashboard_uid = new_dashboard['uid'] 

        new_grafana_url = f'{grafana_base_url}/api/dashboards/uid/{new_dashboard_uid}' 

 

        response_new = requests.get(new_grafana_url, headers=headers) 

        print(response_new) 

 

        if response_new.status_code != 200: 

            print('Error:', response_new.content) 

            return { 

                'statusCode': response_new.status_code, 

                'body': json.dumps({'error': response_new.content.decode('utf-8')}) 

            } 

 

        new_dashboard = json.loads(response_new.content) 

        print(new_dashboard) 

 

        panels_to_update = [panel['title'] for panel in new_dashboard['dashboard']['panels']] 

        print("Panels to update:", panels_to_update) 

 

        # Update panels' data source and URLs 

        for panel in new_dashboard['dashboard']['panels']: 

            for target in panel['targets']: 

                target['datasource']['type'] = 'yesoreyeram-infinity-datasource' 

                target['url'] = s3_url 

            print("Updated panel URL:", s3_url) 

 

        # Save the updated dashboard 

        payload['dashboard'] = new_dashboard['dashboard'] 

        response_update = requests.post(f'{grafana_base_url}/api/dashboards/db', headers=headers, json=payload) 

        print("Response Update:", response_update) 

 

        if response_update.status_code != 200: 

            print('Error:', response_update.content) 

            return { 

                'statusCode': response_update.status_code, 

                'body': json.dumps({'error': response_update.content.decode('utf-8')}) 

            } 

 

        print('Dashboard modified successfully') 

        return { 

            'statusCode': 200, 

            'body': json.dumps('Dashboard modified successfully') 

        } 

 

    except Exception as e: 

        print("An error occurred:", str(e)) 

        return { 

            'statusCode': 500, 

            'body': json.dumps({'error': str(e)}) 

        } 
