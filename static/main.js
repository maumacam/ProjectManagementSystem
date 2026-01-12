// Optional: Confirm before delete
document.addEventListener('DOMContentLoaded', () => {
    const deleteForms = document.querySelectorAll('form button');
    deleteForms.forEach(button => {
        button.addEventListener('click', (e) => {
            if(!confirm('Are you sure you want to delete this?')){
                e.preventDefault();
            }
        });
    });
});
