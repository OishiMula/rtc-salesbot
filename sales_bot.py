# Twitter sales bot created by Oishi Mula for usage at Raging Teens Clan NFT.
# Copyright (c) 2022, Oishi Mula
# All rights reserved.
# This source code is licensed under the MIT-style license found in the
# LICENSE file in the root directory of this source tree. 
import logging
import os
import pickle
import time
from pathlib import Path

import requests
import tweepy
from dotenv import load_dotenv
from pycoingecko import CoinGeckoAPI
from ratelimit import limits

load_dotenv()
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M'
)

# Creating the Twitter tweepy connection for V1.1 (media_upload)
twitter_v1_1_auth = tweepy.OAuth1UserHandler(
    consumer_key=os.getenv('consumer_key'),
    consumer_secret=os.getenv('consumer_secret'),
    access_token=os.getenv('access_token'),
    access_token_secret=os.getenv('access_token_secret')
)

twitter = tweepy.API(twitter_v1_1_auth)

# Project name and file to store last tweeted information
project = "Raging Teens Clan"
last_tweeted_rtc_file = Path('last_sold.dat')
last_tweeted_furin_file = Path('last_furin_sold.dat')

cg = CoinGeckoAPI()
MINUTE = 60
ada = '₳'

# The function to retrieve the JSON listings
def retrieve_sales(p, page_num):
    # These endpoints can be changed, either with a .env or hard-code a URL.
    r_endpoint = f"https://api.opencnft.io/1/policy/{os.getenv('rtc_policyid')}/transactions?page={page_num}&order=date"
    f_endpoint = f"https://api.opencnft.io/1/policy/{os.getenv('furin_policyid')}/transactions?page={page_num}&order=date"
    try:
        match p:
            case 'rtc':
                opencnft_response = requests.get(f'{r_endpoint}')
            case 'furin':
                opencnft_response = requests.get(f'{f_endpoint}')
        return opencnft_response.json()
    except requests.exceptions.RequestException as e:
        logging.error(e)
        time.sleep(300)
        return None

# Cycle through the pages on OpenCNFT
def next_page(p, page_num):
    page_num += 1
    return retrieve_sales(p, page_num), page_num

def prev_page(p, page_num):
    page_num -= 1
    num = 19
    return retrieve_sales(p, page_num), page_num, num

def compare_listing(project, file):
    # setting enviroment up
    check_flag = True
    num = 0
    page_num = 1
    total_listings = 0

    last_tweeted = pickle.load(open(file, 'rb'))
    cnft_listing = retrieve_sales(project, page_num)
    if cnft_listing == None:
        time.sleep(120)
        return
        
    while check_flag == True:
        # Check the listing downloaded and compare to what was last tweeted
        # If downloaded listing is newer, check the next listing / page
        if int(cnft_listing['items'][num]['sold_at']) > int(last_tweeted['sold_at']):
            total_listings += 1
            num += 1
            logging.info(f"Listing #{total_listings} - {cnft_listing['items'][num]['unit_name']} is a new sale. Checking next listing.")
            if num == 20:
                logging.info("Retrieving next page listings.")
                num = 0
                (cnft_listing, page_num) = next_page('rtc', page_num)
            time.sleep(1)

        # If there were new listings, begin to tweet them from oldest to newest.
        elif num > 0:
            logging.info(f"Found {total_listings} listing{'' if total_listings == 1 else 's'}.")
            while num > 0 or page_num > 1:
                num -= 1
                tweet_sale(cnft_listing['items'][num])
                if num == 0 and page_num > 1:
                    (cnft_listing, page_num, num) = prev_page('rtc', page_num)
                time.sleep(3)
            pickle.dump(cnft_listing['items'][num], open(file, 'wb'))
            check_flag = False
            
        # If there was nothing new - skip to end.
        else:
            check_flag = False 

# Creating a payload message to tweet
def tweet_sale(listing):
    asset = listing['unit_name']
    sold_price = int(float(listing['price']) / 1000000)
    asset_mp = listing['marketplace']
    asset_img_raw = listing['thumbnail']['thumbnail'][7:]
    asset_media_id = retrieve_media_id(asset_img_raw)

    # Making exception incase CoinGecko / Twitter are having issues
    while True:
        try:
            usd = cg.get_price(ids='cardano', vs_currencies='usd')
            logging.info(f"{asset} - Purchased for {ada}{sold_price:,}")
            twitter.update_status(status=f"{asset} was purchased from {asset_mp} for the price of {ada}{sold_price:,} (${(usd['cardano']['usd'] * sold_price):,.2f}).", media_ids=[asset_media_id.media_id])
            break
        except (requests.exceptions.RequestException, tweepy.TweepyException) as e:
            logging.error(e)
            time.sleep(15)
            continue        

def retrieve_media_id(img_raw):
    ipfs_base = 'https://infura-ipfs.io/ipfs/'
    asset_img = requests.get(f"{ipfs_base}{img_raw}")
    if asset_img.status_code == 200:
        with open("image.png", 'wb') as f:
            f.write(asset_img.content)
            media_id = twitter.media_upload("image.png")
        os.remove('image.png')
        return media_id
    else:
        return twitter.media_upload("404.jpg")


@limits(calls=30, period=MINUTE)
def main():
    # Upon starting, it will check for a last_sold files. If none exist, it will enter the most recent sale to begin the monitor.
    logging.info(f"Starting the {project} Twitter bot.")
    if last_tweeted_rtc_file.is_file() == False:
        logging.warning(f"{last_tweeted_rtc_file} not found. Creating file now.")
        cnft_listing = retrieve_sales('rtc', 1)
        pickle.dump(cnft_listing['items'][0], open(last_tweeted_rtc_file, 'wb'))
    if last_tweeted_furin_file.is_file() == False:
        logging.warning(f"{last_tweeted_furin_file} not found. Creating file now.")
        cnft_listing = retrieve_sales('furin', 1)
        pickle.dump(cnft_listing['items'][0], open(last_tweeted_furin_file, 'wb'))

    while True:
        raging_teens = 'rtc'
        furins = 'furin'

        # The main function to post on twitter if changes are detected
        compare_listing(raging_teens, last_tweeted_rtc_file)
        compare_listing(furins, last_tweeted_furin_file)
        time.sleep(30)

if __name__ == "__main__":
    main()
