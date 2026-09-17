// Keeps the "Total selected" readout in sync with the block checkboxes.
document.addEventListener('DOMContentLoaded', () => {
  const blockInputs = document.querySelectorAll('input[name="block"]');
  const total = document.getElementById('block-total');
  if (!blockInputs.length || !total) return;

  function updateTotal() {
    let minutes = 0;
    blockInputs.forEach((input) => {
      if (input.checked) minutes += Number(input.dataset.minutes || 0);
    });
    total.textContent = `Total selected: ${minutes} minutes`;
  }

  blockInputs.forEach((input) => input.addEventListener('change', updateTotal));
  updateTotal();
});
