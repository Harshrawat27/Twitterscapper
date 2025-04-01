document.addEventListener('DOMContentLoaded', function () {
  const analyzeBtn = document.getElementById('analyze-btn');
  const profileUrlInput = document.getElementById('profile-url');
  const errorMessage = document.getElementById('error-message');
  const loadingDiv = document.getElementById('loading');
  const resultsDiv = document.getElementById('results');
  const profileInfoDiv = document.getElementById('profile-info');
  const profileNameElement = document.getElementById('profile-name');
  const profileHandleElement = document.getElementById('profile-handle');
  const tweetsContainer = document.getElementById('tweets-container');
  const progressBar = document.getElementById('progress');
  const statusMessage = document.getElementById('status-message');
  const maxTweetsInput = document.getElementById('max-tweets');

  let progressInterval = null;

  analyzeBtn.addEventListener('click', analyzeTweets);

  function analyzeTweets() {
    const profileUrl = profileUrlInput.value;
    const maxTweets = parseInt(maxTweetsInput.value) || 100;

    // Simple validation
    if (!profileUrl) {
      showError('Please enter a valid X profile URL');
      return;
    }

    if (
      !profileUrl.match(
        /^https?:\/\/(www\.)?(twitter|x)\.com\/[a-zA-Z0-9_]{1,15}\/?$/
      )
    ) {
      showError(
        'Please enter a valid X profile URL (e.g., https://x.com/username)'
      );
      return;
    }

    // Hide error message if previously shown
    errorMessage.style.display = 'none';

    // Show loading state
    loadingDiv.style.display = 'block';
    progressBar.style.width = '0%';
    statusMessage.textContent = 'Starting analysis...';

    // Hide results if previously shown
    resultsDiv.style.display = 'none';
    profileInfoDiv.style.display = 'none';

    // Disable the button while processing
    analyzeBtn.disabled = true;

    // Extract username from URL
    const username = profileUrl.split('/').pop().replace('@', '');

    // Set profile info immediately
    profileNameElement.textContent = username;
    profileHandleElement.textContent = `@${username}`;
    profileInfoDiv.style.display = 'block';

    // Make API request to start scraping
    fetch('/api/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        profile_url: profileUrl,
        max_tweets: maxTweets,
      }),
    })
      .then((response) => {
        if (!response.ok) {
          return response.json().then((data) => {
            throw new Error(data.error || 'Failed to analyze profile');
          });
        }
        return response.json();
      })
      .then((data) => {
        // Start polling for progress
        startProgressPolling();
      })
      .catch((error) => {
        showError(
          error.message || 'An error occurred while analyzing the profile'
        );
        analyzeBtn.disabled = false;
      });
  }

  function formatTimeRemaining(seconds) {
    if (seconds < 60) {
      return `${seconds} second${seconds !== 1 ? 's' : ''}`;
    } else if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      return `${minutes} minute${minutes !== 1 ? 's' : ''}`;
    } else {
      const hours = Math.floor(seconds / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      return `${hours} hour${hours !== 1 ? 's' : ''} ${minutes} minute${
        minutes !== 1 ? 's' : ''
      }`;
    }
  }

  function startProgressPolling() {
    // Clear any existing polling
    if (progressInterval) {
      clearInterval(progressInterval);
    }

    // Poll every second
    progressInterval = setInterval(checkProgress, 1000);
  }

  function checkProgress() {
    fetch('/api/progress')
      .then((response) => response.json())
      .then((data) => {
        // Update the progress display
        const percent =
          data.total_expected > 0
            ? Math.min(
                Math.round((data.tweets_scraped / data.total_expected) * 100),
                100
              )
            : 0;

        progressBar.style.width = `${percent}%`;

        // Update status message with tweet count and time remaining
        let statusText = `Analyzed ${data.tweets_scraped} of ${data.total_expected} tweets`;

        if (data.estimated_time_remaining > 0 && data.status !== 'complete') {
          statusText += ` - Estimated time remaining: ${formatTimeRemaining(
            data.estimated_time_remaining
          )}`;
        }

        statusMessage.textContent = statusText;

        // Check if scraping is complete
        if (data.status === 'complete' && data.top_tweets) {
          clearInterval(progressInterval);
          progressInterval = null;

          // Display tweets
          displayTweets(data.top_tweets);

          // Update status message with total tweets analyzed
          statusMessage.textContent = `Analyzed ${data.total_tweets_analyzed} tweets`;
          progressBar.style.width = '100%';

          // Show results
          resultsDiv.style.display = 'block';

          // Re-enable the button
          analyzeBtn.disabled = false;
        } else if (data.status === 'error') {
          clearInterval(progressInterval);
          progressInterval = null;
          showError('An error occurred during scraping');
          analyzeBtn.disabled = false;
        }
      })
      .catch((error) => {
        console.error('Error checking progress:', error);
      });
  }

  function displayTweets(tweets) {
    tweetsContainer.innerHTML = ''; // Clear previous results

    if (!tweets || tweets.length === 0) {
      tweetsContainer.innerHTML =
        '<p>No tweets found or unable to analyze tweets.</p>';
      return;
    }

    tweets.forEach((tweet) => {
      const tweetCard = document.createElement('div');
      tweetCard.className = 'tweet-card';

      // Format the date from ISO string
      let dateDisplay = tweet.display_time;
      if (tweet.timestamp) {
        try {
          const tweetDate = new Date(tweet.timestamp);
          dateDisplay = tweetDate.toLocaleString();
        } catch (e) {
          console.error('Error formatting date:', e);
        }
      }

      tweetCard.innerHTML = `
                <div class="tweet-header">
                    <div class="tweet-user">
                        <h3>${tweet.username || 'Unknown User'}</h3>
                        <span>${tweet.handle || ''} · ${dateDisplay}</span>
                    </div>
                </div>
                <div class="tweet-content">
                    ${tweet.text || 'No text available'}
                </div>
                <div class="tweet-stats">
                    <div class="stat">
                        <svg viewBox="0 0 24 24" fill="#657786">
                            <path d="M1.751 10c0-4.42 3.584-8 8.005-8h4.366c4.49 0 8.129 3.64 8.129 8.13 0 2.96-1.607 5.68-4.196 7.11l-8.054 4.46v-3.69h-.067c-4.49.1-8.183-3.51-8.183-8.01z"></path>
                        </svg>
                        ${tweet.replies || 0}
                    </div>
                    <div class="stat">
                        <svg viewBox="0 0 24 24" fill="#657786">
                            <path d="M4.5 3.88l4.432 4.14-1.364 1.46L5.5 7.55V16c0 1.1.896 2 2 2H13v2H7.5c-2.209 0-4-1.79-4-4V7.55L1.432 9.48.068 8.02 4.5 3.88zM16.5 6H11V4h5.5c2.209 0 4 1.79 4 4v8.45l2.068-1.93 1.364 1.46-4.432 4.14-4.432-4.14 1.364-1.46 2.068 1.93V8c0-1.1-.896-2-2-2z"></path>
                        </svg>
                        ${tweet.retweets || 0}
                    </div>
                    <div class="stat">
                        <svg viewBox="0 0 24 24" fill="#657786">
                            <path d="M16.697 5.5c-1.222-.06-2.679.51-3.89 2.16l-.805 1.09-.806-1.09C9.984 6.01 8.526 5.44 7.304 5.5c-1.243.07-2.349.78-2.91 1.91-.552 1.12-.633 2.78.479 4.82 1.074 1.97 3.257 4.27 7.129 6.61 3.87-2.34 6.052-4.64 7.126-6.61 1.111-2.04 1.03-3.7.477-4.82-.561-1.13-1.666-1.84-2.908-1.91z"></path>
                        </svg>
                        ${tweet.likes || 0}
                    </div>
                    <div class="stat">
                        <svg viewBox="0 0 24 24" fill="#657786">
                            <path d="M8.75 21V3h2v18h-2zM18 21V8.5h2V21h-2zM4 21l.004-10h2L6 21H4zm9.248 0v-7h2v7h-2z"></path>
                        </svg>
                        ${(tweet.views || 0).toLocaleString()}
                    </div>
                    <div class="engagement-score">
                        ${
                          tweet.engagement_score
                            ? tweet.engagement_score.toFixed(1) + '%'
                            : '0%'
                        }
                    </div>
                </div>
                ${
                  tweet.url
                    ? `<a href="${tweet.url}" target="_blank" class="tweet-link">View Tweet</a>`
                    : ''
                }
            `;

      tweetsContainer.appendChild(tweetCard);
    });
  }

  function showError(message) {
    errorMessage.textContent = message;
    errorMessage.style.display = 'block';
    loadingDiv.style.display = 'none';
  }
});
