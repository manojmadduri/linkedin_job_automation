# LinkedIn Job Automation

This script automates the process of finding and responding to job postings on LinkedIn. It searches for posts related to Java Developer positions, filters for recent posts (past 24 hours), and automatically sends personalized emails to US-based contract/C2C job opportunities.

## Features

- **Automated LinkedIn Search**: Searches for "Java Developer" posts on LinkedIn
- **Post Filtering**: Automatically selects the "Posts" tab and filters for posts from the past 24 hours
- **US Job Detection**: Identifies US-based job opportunities using location keywords and zip code patterns
- **Contract/C2C Detection**: Only responds to contract or C2C positions
- **Candidate Post Filtering**: Skips posts from candidates who are looking for jobs
- **Email Extraction**: Extracts email addresses from posts using multiple pattern matching techniques
- **Resume-Based Responses**: Uses your resume to generate personalized email responses
- **Automated Email Responses**: Generates personalized email responses using OpenAI's GPT model
- **Continuous Operation**: Runs continuously without requiring manual confirmation to continue searching
- **Response Tracking**: Keeps track of posts that have already been responded to
- **Email Domain Tracking**: Prevents sending multiple emails to the same domain in a single day
- **Personalization**: Includes your name, phone number, and email in the generated responses

## Prerequisites

- Python 3.6+
- Chrome browser
- ChromeDriver (compatible with your Chrome version)
- LinkedIn account
- Gmail account with app password
- OpenAI API key

## Installation

1. Clone this repository:
```
git clone https://github.com/yourusername/linkedin-job-automation.git
cd linkedin-job-automation
```

2. Install the required packages:
```
pip install -r requirements.txt
```

3. Configure your credentials in `config.json`:
```json
{
    "linkedin_email": "your_linkedin_email@example.com",
    "linkedin_password": "your_linkedin_password",
    "gmail_email": "your_gmail@gmail.com",
    "gmail_app_password": "your_gmail_app_password",
    "openai_api_key": "your_openai_api_key",
    "user_name": "Your Full Name",
    "user_phone": "Your Phone Number",
    "user_email": "your_email@example.com",
    "auto_send_us_jobs": true
}
```

4. Add your resume (optional but recommended):
Create a file named `resume.txt` or `resume.md` in the project directory with your resume content. The script will use this to generate more personalized email responses.

## Usage

Run the script:
```
python linkedin_automation.py
```

The script will:
1. Log in to your LinkedIn account
2. Search for "Java Developer" posts
3. Click on the "Posts" tab
4. Sort by "Recent" and filter for "Past 24 hours"
5. Process posts to find those with email addresses
6. For US-based contract/C2C job opportunities:
   - Generate a personalized email response using OpenAI and your resume
   - Automatically send the email from your Gmail account
7. Continue searching and processing posts without requiring manual confirmation
8. Track which posts have already been responded to
9. Prevent sending multiple emails to the same domain in a single day

## Continuous Operation Mode

The script operates in a continuous mode:
- It will keep searching for new posts without asking for confirmation
- It automatically scrolls to load more posts
- When it reaches the end of available posts, it will restart the search
- You can stop the script at any time by pressing Ctrl+C

## Smart Filtering

The script applies several filters to ensure it only responds to relevant job postings:
- Only responds to US-based job opportunities
- Only responds to contract/C2C positions
- Skips posts from candidates who are looking for jobs
- Doesn't send multiple emails to the same domain in a single day
- Avoids responding to the same post multiple times

## Configuration Options

- `linkedin_email`: Your LinkedIn login email
- `linkedin_password`: Your LinkedIn password
- `gmail_email`: Your Gmail address for sending responses
- `gmail_app_password`: Your Gmail app password (not your regular Gmail password)
- `openai_api_key`: Your OpenAI API key for generating email content
- `user_name`: Your full name (included in email responses)
- `user_phone`: Your phone number (included in email responses)
- `user_email`: Your email address (included in email responses)
- `auto_send_us_jobs`: Set to `true` to automatically send emails without confirmation

## Troubleshooting

- If the script fails to find the Posts tab, it will take a screenshot and save the page source for debugging
- Check the log file for detailed error messages
- Make sure your LinkedIn and Gmail credentials are correct
- Verify that your Gmail account has "Less secure app access" enabled or that you're using an app password

## License

This project is licensed under the MIT License - see the LICENSE file for details.
