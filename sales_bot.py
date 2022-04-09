# Twitter sales bot created by Oishi Mula for usage at Raging Teens Clan NFT.
# Copyright (c) 2022, Oishi Mula
# All rights reserved.
# This source code is licensed under the MIT-style license found in the
# LICENSE file in the root directory of this source tree. 
import math
import os
import pickle
import time
from pathlib import Path

import requests
import tweepy
from dotenv import load_dotenv
from ratelimit import limits

load_dotenv()

# Creating the Twitter tweepy connection for V1.1 (media_upload)
twitter_v1_1_auth = tweepy.OAuth1UserHandler(
    consumer_key=os.getenv('consumer_key'),
    consumer_secret=os.getenv('consumer_secret'),
    access_token=os.getenv('access_token'),
    access_token_secret=os.getenv('access_token_secret')
)

twitter = tweepy.API(twitter_v1_1_auth)

# Creating a first run to see if the file to store last transaciton is made
first_run = True
last_sold_file = Path('last_sold.dat')
last_sold_furin_file = Path('last_furin_sold.dat')

running = True
MINUTE = 60
ada = '₳'

millnames = ['',' K',' M',' B',' T']
def millify(n):
    n = float(n)
    millidx = max(0,min(len(millnames)-1,
                        int(math.floor(0 if n == 0 else math.log10(abs(n))/3))))

    return '{:.0f}{}'.format(n / 10**(3 * millidx), millnames[millidx])

# The function to retrieve the JSON listings
def retrieve_sales(p, page_num):
    # These endpoints can be changed, either with a .env or hard-code a URL.
    r_endpoint = f"https://api.opencnft.io/1/policy/{os.getenv('rtc_policyid')}/transactions?page={page_num}&order=date"
    f_endpoint = f"https://api.opencnft.io/1/policy/{os.getenv('furin_policyid')}/transactions?page={page_num}&order=date"
    match p:
        case 'rtc':
            response_API = requests.get(f'{r_endpoint}')
        case 'furin':
            response_API = requests.get(f'{f_endpoint}')

    if response_API.status_code == 200: return response_API.json()
    else: return None

# Cycle through the pages on OpenCNFT
def next_page(p, page_num):
    page_num += 1
    return retrieve_sales(p, page_num), page_num

def prev_page(p, page_num):
    page_num -= 1
    num = 19
    return retrieve_sales(p, page_num), page_num, num

def compare_listings(project, file):
    # setting enviroment up
    check_flag = True
    num = 0
    page_num = 1
    last_tweeted = pickle.load(open(file, 'rb'))
    current_sales = retrieve_sales(project, page_num)
            
    while check_flag == True:
        print(f"last tweet: {last_tweeted['unit_name']} --- current downloaded: {current_sales['items'][num]['unit_name']}")
        time.sleep(1)
        if int(current_sales['items'][num]['sold_at']) > int(last_tweeted['sold_at']):
            print(f"Listing #{num} - {current_sales['items'][num]['unit_name']} is newer then {last_tweeted['unit_name']}. Checking next listing ")
            num += 1
            print(f"Checking listing #{num}")
            if num == 20:
                print("Retrieving more listings.")
                num = 0
                (current_sales, page_num) = next_page('rtc', page_num)
            time.sleep(1)

        elif num > 0 or num == 19:
            print(page_num)
            if page_num > 1:
                total_listings = (page_num - 1) * 19 + num
            else:
                total_listings = num
            print(f"Found: {total_listings} listings. Beginning to tweet.")
            while num > 0 or page_num > 1:
                num -= 1
                print(f"Tweeting: {current_sales['items'][num]['unit_name']}")
                tweet_sale(current_sales['items'][num])
                if num == 0 and page_num > 1:
                    (current_sales, page_num, num) = prev_page('rtc', page_num)
                time.sleep(3)
            pickle.dump(current_sales['items'][num], open(file, 'wb'))
            check_flag = False

        else:
            check_flag = False
            print("Passing")  

# Functions to make media uploads and tweets.
def tweet_sale(listing):
    asset = listing['unit_name']
    sold_price = int(float(listing['price']) / 1000000)
    asset_mp = listing['marketplace']
    asset_img_raw = listing['thumbnail']['thumbnail'][7:]
    asset_media_id = retrieve_media_id(asset_img_raw)

    twitter.update_status(status=f"{asset} was purchased from {asset_mp} for the price of {ada}{millify(sold_price)}.", media_ids=[asset_media_id.media_id])
    os.remove('image.png')

def retrieve_media_id(img_raw):
    ipfs_base = 'https://infura-ipfs.io/ipfs/'
    asset_img = requests.get(f"{ipfs_base}{img_raw}")
    if asset_img.status_code == 200:
        with open("image.png", 'wb') as f:
            f.write(asset_img.content)
            return twitter.media_upload("image.png")
    else:
        return twitter.media_upload("404.jpg")

@limits(calls=30, period=MINUTE)
def main():
    global first_run
    global running

    # Upon starting, it will check for a last_sold file. If none exist, it will enter the most recent sale to begin the monitor.
    if first_run == True:
        first_run = False
        if last_sold_file.is_file() == False:
            current_sales_rtc = retrieve_sales('rtc', 1)
            pickle.dump(current_sales_rtc['items'][2], open(last_sold_file, 'wb'))
        if last_sold_furin_file.is_file() == False:
            current_sales_furin = retrieve_sales('furin', 1)
            pickle.dump(current_sales_furin['items'][3], open(last_sold_furin_file, 'wb'))

    while running == True:
        raging_teens = 'rtc'
        furins = 'furin'

        # The main function to post on twitter if changes are detected
        compare_listings(raging_teens, last_sold_file)
        compare_listings(furins, last_sold_furin_file)

        time.sleep(30)

if __name__ == "__main__":
    main()
