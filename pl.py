import json
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
import nest_asyncio

# Allow nested event loops in Jupyter
nest_asyncio.apply()

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
            try:
                phone_no = await page.evaluate('document.querySelector("div.contact-container a:nth-of-type(2)") ? document.querySelector("div.contact-container a:nth-of-type(2)").href : "Not available"')
                page_data = {
                    "State URL": state_link,
                    "City URL": city_link,
                    "Service URL": service_link,
                    "Phone Number": phone_no
                }
                all_data.append(page_data)
            except Exception as inner_e:
                print(f"Error extracting phone number: {inner_e}")

            links = await page.eval_on_selector_all('//h5[@class="leading-7"]/a', 'elements => elements.map(el => el.href)')
            if links:
                for link in links:
                    await page.goto(link, wait_until='networkidle', timeout=60000)
                    phone_no = await page.evaluate('document.querySelector("div.contact-container a:nth-of-type(2)") ? document.querySelector("div.contact-container a:nth-of-type(2)").href : "Not available"')
                    page_data = {
                        "State URL": state_link,
                        "City URL": city_link,
                        "Service URL": service_link,
                        "Phone Number": phone_no
                    }
                    all_data.append(page_data)
            else:
                print(f"No links found for URL: {service_link}")

    except Exception as e:
        print(f"Error scraping {service_link}: {e}")

    finally:
        # Save data to CSV after each link attempt
        df = pd.DataFrame(all_data)
        df.to_csv('/Data/scraped_next_data12524323435521.csv', index=False)
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
            states_links = states_links[5:]  # Modify as needed
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
                        for service_link in service_links[i:i+4]:  # Open 4 links (tabs) at the same time
                            tasks.append(scrape_service_link(browser, service_link, state_link, city_link, all_data))

                        await asyncio.gather(*tasks)

            await browser.close()

    except Exception as e:
        print(f"Error during scraping: {e}")
        # Save any data that has been collected so far before exiting
        df = pd.DataFrame(all_data)
        df.to_csv('/Data/scraped_next_data_error132545445.csv', index=False)
        print(f"Error encountered. Data saved to 'scraped_next_data_error14545445.csv'. Total records: {len(all_data)}")

# Run the async function in Jupyter Notebook
await get_next_data()
