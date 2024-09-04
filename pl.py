import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import nest_asyncio
nest_asyncio.apply()
async def run_playwright_test():
    all_data = []  # List to store scraped data
    
    async with async_playwright() as p:
        # Launch the browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Navigate to a website
        await page.goto('https://example.com', wait_until='networkidle', timeout=30000)
        
        # Sample data extraction
        title = await page.title()
        url = page.url
        
        # Add extracted data to the list
        all_data.append({"URL": url, "Title": title})
        
        # Save data to CSV
        df = pd.DataFrame(all_data)
        print(df)
        df.to_csv('scraped_data.csv', index=False)
        print('Data saved to scraped_data.csv')
        
        # Close the browser
        await browser.close()

# Run the async function
asyncio.run(run_playwright_test())
