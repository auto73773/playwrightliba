import json
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
import nest_asyncio
import dropbox
from io import StringIO
import os
# Allow nested event loops in Jupyter
nest_asyncio.apply()

ACCESS_TOKEN=os.getenv('DROPBOX_ACCESS_TOKEN')
# Initialize Dropbox client with your access token
dbx = dropbox.Dropbox(ACCESS_TOKEN)

# Dropbox upload function
def upload_data_to_dropbox(data_content, dropbox_path):
    try:
        # Convert the data to bytes (assuming data_content is already in string format)
        data_bytes = data_content.encode('utf-8')
        dbx.files_upload(data_bytes, dropbox_path, mode=dropbox.files.WriteMode('overwrite'))
        print(f"Uploaded data to {dropbox_path}")
    except dropbox.exceptions.ApiError as err:
        print(f"Failed to upload data to {dropbox_path}: {err}")

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
                "Page Data": json.dumps(next_data)
            }
            all_data.append(page_data)
        else:
            print(f"No __NEXT_DATA__ found for URL: {service_link}")

    except Exception as e:
        print(f"Error scraping {service_link}: {e}")

    finally:
        # Convert the scraped data (stored in `all_data` list) to a CSV string
        df = pd.DataFrame(all_data)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()

        # Upload CSV string to Dropbox (overwrite mode)
        dropbox_file_path = '/scraped_next_data.csv'
        upload_data_to_dropbox(csv_data, dropbox_file_path)

        await page.close()

# Main function to scrape data
async def get_next_data():
    all_data = []  # Store all scraped data

    try:
        async with async_playwright() as p:
            # Launch the browser
            browser = await p.chromium.launch(headless=True, args=['--disable-gpu', '--disable-blink-features=AutomationControlled'])
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
            page = await context.new_page()
            await page.goto('https://www.homeadvisor.com/clp/', wait_until='networkidle', timeout=60000)

            states_links = await page.eval_on_selector_all('div.state-list-container ul li a', 'elements => elements.map(el => el.href)')
            print(f"Found {len(states_links)} state links.")
            states_links = states_links[5:]

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
                    for i in range(0, len(service_links), 4):
                        tasks = []
                        for service_link in service_links[i:i+2]:  # Open 2 links (tabs) at the same time
                            tasks.append(scrape_service_link(browser, service_link, state_link, city_link, all_data))

                        await asyncio.gather(*tasks)

            await browser.close()

    except Exception as e:
        print(f"Error during scraping: {e}")
        # Save any data that has been collected so far before exiting
        df = pd.DataFrame(all_data)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()
        upload_data_to_dropbox(csv_data, '/scraped_next_data_error.csv')
        print(f"Error encountered. Data uploaded to Dropbox. Total records: {len(all_data)}")

# Run the async function in Jupyter Notebook
asyncio.run(get_next_data())
