import json
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
import nest_asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from io import BytesIO
import time
from datetime import datetime
import os

# Allow nested event loops in Jupyter
nest_asyncio.apply()

def generate_unique_filename(base_name):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{base_name}_{timestamp}.json"

# Load JSON data from file.json
with open('file.json', 'r') as f:
    key_data = json.load(f)

# Initialize Google Drive client
SCOPES = ['https://www.googleapis.com/auth/drive.file']
SERVICE_ACCOUNT_FILE = key_data
credentials = service_account.Credentials.from_service_account_info(key_data, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# Google Drive upload function for JSON data
def upload_data_to_drive_json(data_content, folder_id, filename):
    try:
        # Convert the JSON data to bytes
        data_bytes = data_content.encode('utf-8')
        
        # Use BytesIO to create a file-like object from the bytes data
        data_stream = BytesIO(data_bytes)

        # Generate a unique filename or use a fixed one
        unique_filename = generate_unique_filename(filename)  # Or use a fixed name

        # Check if the file exists and delete if necessary
        existing_files = drive_service.files().list(
            q=f"'{folder_id}' in parents and name='{unique_filename}'",
            spaces='drive',
            fields='files(id, name)'
        ).execute().get('files', [])

        for item in existing_files:
            drive_service.files().delete(fileId=item['id']).execute()
            print(f"Deleted existing file with name {unique_filename}")

        # Upload the file
        media = MediaIoBaseUpload(data_stream, mimetype='application/json')
        file_metadata = {
            'name': unique_filename,
            'parents': [folder_id]
        }
        drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name'
        ).execute()
        print(f"Uploaded data to Google Drive folder ID {folder_id} with filename {unique_filename}")
    except Exception as err:
        print(f"Failed to upload data to Google Drive: {err}")

# Function to scrape a single service link using a new tab
async def scrape_service_link(browser, service_link, state_link, city_link, all_data):
    page = await browser.new_page()  # Open a new tab
    try:
        await page.route('**/*.{png,jpg,jpeg,gif,webp}', lambda route: route.abort())
        await page.route('**/*.css', lambda route: route.abort())

        await page.goto(service_link, wait_until='networkidle', timeout=60000)

        # Check for __NEXT_DATA__ element and extract if available
        next_data_exists = await page.evaluate('document.getElementById("__NEXT_DATA__") !== null')

        if next_data_exists:
            next_data_content = await page.evaluate('document.getElementById("__NEXT_DATA__").innerText')
            next_data = json.loads(next_data_content)

            # Store the extracted data
            page_data = {
                "State URL": state_link,
                "City URL": city_link,
                "Service URL": service_link,
                "Page Data": next_data
            }
            all_data.append(page_data)
        else:
            print(f"No __NEXT_DATA__ found for URL: {service_link}")

    except Exception as e:
        print(f"Error scraping {service_link}: {e}")

    finally:
        await page.close()

# Main function to scrape data with 1-minute uploads
async def get_next_data():
    all_data = []  # Store all scraped data
    start_time = time.time()  # Record the start time

    try:
        async with async_playwright() as p:
            # Launch the browser
            browser = await p.chromium.launch(headless=True, args=['--disable-gpu', '--disable-blink-features=AutomationControlled'])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            page = await context.new_page()
            await page.goto('https://www.homeadvisor.com/clp/', wait_until='networkidle', timeout=60000)

            states_links = await page.eval_on_selector_all('div.state-list-container ul li a', 'elements => elements.map(el => el.href)')
            print(f"Found {len(states_links)} state links.")
            states_links = states_links[23:]

            # Loop through each state link
            for state_link in states_links:
                await page.goto(state_link, wait_until='networkidle', timeout=60000)
                city_links = await page.eval_on_selector_all('div.t-more-projects-accordion-list ul li a', 'elements => elements.map(el => el.href)')
                print(f"Found {len(city_links)} city links for state: {state_link}")

                # Loop through each city link
                for city_link in city_links:
                    await page.goto(city_link, wait_until='networkidle', timeout=60000)
                    service_links = await page.eval_on_selector_all('div.xmd-content-main ul li a', 'elements => elements.map(el => el.href)')
                    print(f"Found {len(service_links)} service links for city: {city_link}")

                    # Limit to 4 concurrent tasks for service links
                    for i in range(0, len(service_links), 10):
                        tasks = []
                        for service_link in service_links[i:i+10]:  # Open 10 links (tabs) at the same time
                            tasks.append(scrape_service_link(browser, service_link, state_link, city_link, all_data))

                        await asyncio.gather(*tasks)

                    # Check if 1 minute has passed since the last upload
                    if time.time() - start_time >= 1200:  # 60 seconds = 1 minute
                        json_data = json.dumps(all_data, indent=4)
                        drive_folder_id = '11cJWbuEbwFcmwT7MNArfNWsN5Jh466Wg'  # Replace with your Google Drive folder ID
                        filename = 'scraped_next_data.json'  # File to overwrite
                        upload_data_to_drive_json(json_data, drive_folder_id, filename)

                        # Reset start time for the next minute
                        start_time = time.time()
                        print(f"Data uploaded to Google Drive after 1 minute. Total records: {len(all_data)}")

            await browser.close()

        # Final upload after all scraping is done
        json_data = json.dumps(all_data, indent=4)
        drive_folder_id = '11cJWbuEbwFcmwT7MNArfNWsN5Jh466Wg'  # Replace with your Google Drive folder ID
        filename = 'scraped_next_data_final.json'
        upload_data_to_drive_json(json_data, drive_folder_id, filename)
        print(f"Final data upload complete. Total records: {len(all_data)}")

    except Exception as e:
        print(f"Error during scraping: {e}")
        # Save any data that has been collected so far before exiting
        json_data = json.dumps(all_data, indent=4)
        drive_folder_id = '11cJWbuEbwFcmwT7MNArfNWsN5Jh466Wg'  # Replace with your Google Drive folder ID
        filename = 'scraped_next_data_error.json'
        upload_data_to_drive_json(json_data, drive_folder_id, filename)
        print(f"Error encountered. Data uploaded to Google Drive. Total records: {len(all_data)}")

# Run the async function
asyncio.run(get_next_data())
