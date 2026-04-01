document.addEventListener("DOMContentLoaded", () => {
    // Basic interaction: Simple Search Filter for Blog Posts
    const searchInput = document.getElementById("searchInput");
    const blogCards = document.querySelectorAll(".blog-card");

    if (searchInput) {
        searchInput.addEventListener("keyup", function(e) {
            const term = e.target.value.toLowerCase();

            blogCards.forEach(card => {
                const title = card.querySelector("h3").textContent.toLowerCase();
                const excerpt = card.querySelector("p").textContent.toLowerCase();

                if (title.includes(term) || excerpt.includes(term)) {
                    card.style.display = "block";
                } else {
                    card.style.display = "none";
                }
            });
        });
    }

    // MCQ Selection Interaction
    const mcqOptions = document.querySelectorAll(".mcq-options span");
    mcqOptions.forEach(option => {
        option.addEventListener("click", function() {
            // Remove active styles from siblings
            this.parentElement.querySelectorAll("span").forEach(el => {
                el.style.backgroundColor = "";
                el.style.color = "";
                el.style.borderColor = "";
            });
            // Apply active styles (Medium/Stripe style selection)
            this.style.backgroundColor = "rgba(37, 99, 235, 0.1)"; // Primary transparent
            this.style.borderColor = "#2563eb"; // Primary color
            this.style.color = "#2563eb";
        });
    });
});
