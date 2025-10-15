document.addEventListener('DOMContentLoaded', () => {
    const quoteContainer = document.getElementById('quote-container');
    const timerElement = document.getElementById('timer');
    let timer;

    function getRandomQuotes() {
        const shuffled = quotes.sort(() => 0.5 - Math.random());
        return shuffled.slice(0, 5);
    }

    function displayQuotes() {
        quoteContainer.innerHTML = '';
        const randomQuotes = getRandomQuotes();
        randomQuotes.forEach(quote => {
            const quoteElement = document.createElement('div');
            quoteElement.classList.add('quote');
            quoteElement.innerHTML = `
                <p>"${quote.text}"</p>
                <div class="quote-footer">
                    <footer>- ${quote.author}</footer>
                    <button class="copy-btn">نسخ</button>
                </div>
            `;
            quoteContainer.appendChild(quoteElement);
        });

        addCopyEventListeners();
    }

    function addCopyEventListeners() {
        const copyButtons = document.querySelectorAll('.copy-btn');
        copyButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                const quoteText = e.target.parentElement.querySelector('p').innerText;
                navigator.clipboard.writeText(quoteText).then(() => {
                    e.target.innerText = 'تم النسخ!';
                    setTimeout(() => {
                        e.target.innerText = 'نسخ';
                    }, 2000);
                });
            });
        });
    }

    function startTimer() {
        let timeLeft = 30;
        timerElement.innerText = timeLeft;

        timer = setInterval(() => {
            timeLeft--;
            timerElement.innerText = timeLeft;
            if (timeLeft === 0) {
                clearInterval(timer);
                displayQuotes();
                startTimer();
            }
        }, 1000);
    }

    displayQuotes();
    startTimer();
});
