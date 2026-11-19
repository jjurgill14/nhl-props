import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome', args=['--no-sandbox'])
        pg = await b.new_page(viewport={'width':1400,'height':1100})
        await pg.goto('file://' + sys.argv[2] + '')
        await pg.wait_for_timeout(1500)
        # open lineups for the first game
        await pg.click('aside.rail button[aria-label="Lines & lineups"]')
        await pg.wait_for_timeout(2500)
        await pg.screenshot(path=sys.argv[1])
        await b.close()
asyncio.run(main())
