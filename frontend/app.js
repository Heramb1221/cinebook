// =============================================================
// CineBook frontend app
// Talks to the Flask/DynamoDB backend via API_BASE_URL (config.js)
// =============================================================

let STATE = {
  movies: [],
  currentMovie: null,
  currentDate: null,
  currentShow: null,   // { show_id, theatre, show_date, show_time }
  bookedSeats: [],      // seat_ids already taken for currentShow
  selectedSeats: [],     // [{seat_id, seat_type, price}]
};

const SEAT_ROWS = [
  { label: 'A', type: 'recliner', price: 550, count: 8 },
  { label: 'B', type: 'recliner', price: 550, count: 8 },
  { label: 'C', type: 'premium', price: 350, count: 10 },
  { label: 'D', type: 'premium', price: 350, count: 10 },
  { label: 'E', type: 'premium', price: 350, count: 10 },
  { label: 'F', type: 'standard', price: 200, count: 12 },
  { label: 'G', type: 'standard', price: 200, count: 12 },
  { label: 'H', type: 'standard', price: 200, count: 12 },
];

// ---------------- API helpers ----------------
async function apiGet(path) {
  const res = await fetch(`${API_BASE_URL}${path}`);
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data;
}
async function apiPost(path, body) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data;
}
async function apiDelete(path) {
  const res = await fetch(`${API_BASE_URL}${path}`, { method: 'DELETE' });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data };
  return data;
}

function showToast(msg, isError = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), 3200);
}

// ---------------- View switching ----------------
function showView(id) {
  ['homeView', 'movieView', 'seatView', 'ticketsView'].forEach(v => {
    document.getElementById(v).classList.toggle('hidden', v !== id);
  });
  window.scrollTo(0, 0);
}

function goHome() {
  showView('homeView');
}

// ---------------- Fallback demo data (used if API isn't reachable yet) ----------------
const FALLBACK_MOVIES = [
  { movie_id: 'mv001', title: 'Deep Drift', genre: 'Sci-Fi / Thriller', language: 'English', duration_mins: 148, rating: 'UA', imdb_rating: '8.8', poster_url: 'posters/tt1375666.svg', description: 'A skilled operative who steals secrets from deep within the subconscious is offered a chance at redemption: plant an idea instead of stealing one.' },
  { movie_id: 'mv002', title: 'Beyond the Stars', genre: 'Sci-Fi / Drama', language: 'English', duration_mins: 169, rating: 'UA', imdb_rating: '8.7', poster_url: 'posters/tt0816692.svg', description: "A team of explorers travels through a wormhole in deep space in a desperate attempt to ensure humanity's survival." },
  { movie_id: 'mv003', title: 'Chain Reaction', genre: 'Biography / Drama', language: 'English', duration_mins: 180, rating: 'A', imdb_rating: '8.4', poster_url: 'posters/tt15398776.svg', description: 'The story of a brilliant scientist and his role in a discovery that changes the world forever.' },
  { movie_id: 'mv004', title: 'Vendetta', genre: 'Action / Drama', language: 'Hindi', duration_mins: 169, rating: 'UA', imdb_rating: '7.0', poster_url: 'posters/tt11304740.svg', description: 'A man driven by a personal vendetta sets out to rectify the wrongs in society, fulfilling a promise made years ago.' },
  { movie_id: 'mv005', title: 'Multiverse Protocol', genre: 'Animation / Action', language: 'English', duration_mins: 140, rating: 'U', imdb_rating: '8.6', poster_url: 'posters/tt9362722.svg', description: 'A young hero catapults across the multiverse, encountering a team charged with protecting its very existence.' },
  { movie_id: 'mv006', title: 'The Hidden Nation', genre: 'Action / Adventure', language: 'English', duration_mins: 161, rating: 'UA', imdb_rating: '6.7', poster_url: 'posters/tt6443346.svg', description: 'The people of a hidden nation fight to protect their home from intervening world powers in a time of mourning.' },
];
const THEATRES = ['PVR Lower Parel', 'INOX R-City Mall', 'Cinepolis Andheri'];
const SHOW_TIMES = ['10:00', '13:30', '17:00', '19:30', '22:00'];

function buildShowId(movieId, theatre, date, time) {
  return `${movieId}#${theatre.replace(/ /g, '-')}#${date}#${time}`;
}

// ---------------- Load movies ----------------
async function loadMovies() {
  try {
    const data = await apiGet('/api/movies');
    STATE.movies = data.movies && data.movies.length ? data.movies : FALLBACK_MOVIES;
  } catch (e) {
    console.warn('API unreachable, using fallback demo catalogue', e);
    STATE.movies = FALLBACK_MOVIES;
  }
  renderHero();
  renderMovieGrid();
}

function renderHero() {
  const el = document.getElementById('heroCarousel');
  const slides = STATE.movies.slice(0, 4);
  el.innerHTML = slides.map(m => `
    <div class="hero-slide" style="background-image:url('${m.poster_url}')">
      <div class="hero-slide-content">
        <div class="hero-slide-title">${escapeHtml(m.title)}</div>
        <div class="hero-slide-meta">
          <span class="hero-rating">★ ${m.imdb_rating}</span>
          <span>${escapeHtml(m.genre)}</span>
          <span>•</span>
          <span>${escapeHtml(m.language)}</span>
        </div>
      </div>
    </div>
  `).join('');
}

function renderMovieGrid() {
  const el = document.getElementById('movieGrid');
  el.innerHTML = STATE.movies.map(m => `
    <div class="movie-card" onclick="openMovie('${m.movie_id}')">
      <div class="movie-poster-wrap">
        <img src="${m.poster_url}" alt="${escapeHtml(m.title)} poster" loading="lazy">
        <div class="movie-rating-badge">★ ${m.imdb_rating}</div>
      </div>
      <div class="movie-card-body">
        <div class="movie-card-title">${escapeHtml(m.title)}</div>
        <div class="movie-card-meta">${escapeHtml(m.language)} • ${escapeHtml(m.genre)}</div>
      </div>
    </div>
  `).join('');
}

function escapeHtml(s) {
  if (!s) return '';
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// ---------------- Movie detail / showtimes ----------------
function openMovie(movieId) {
  const movie = STATE.movies.find(m => m.movie_id === movieId);
  if (!movie) return;
  STATE.currentMovie = movie;

  document.getElementById('movieBanner').style.backgroundImage = `url('${movie.poster_url}')`;
  document.getElementById('movieBanner').innerHTML = `
    <div class="movie-banner-content">
      <div class="movie-banner-title">${escapeHtml(movie.title)}</div>
      <div class="movie-banner-tags">
        <span class="tag">★ ${movie.imdb_rating}</span>
        <span class="tag">${escapeHtml(movie.rating)}</span>
        <span class="tag">${movie.duration_mins} min</span>
        <span class="tag">${escapeHtml(movie.language)}</span>
        <span class="tag">${escapeHtml(movie.genre)}</span>
      </div>
      <div class="movie-banner-desc">${escapeHtml(movie.description)}</div>
    </div>
  `;

  renderDateStrip();
  showView('movieView');
}

function renderDateStrip() {
  const el = document.getElementById('dateStrip');
  const dates = [];
  const today = new Date();
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(today.getDate() + i);
    dates.push(d);
  }
  STATE.currentDate = formatDate(dates[0]);
  el.innerHTML = dates.map((d, i) => `
    <button class="date-pill ${i === 0 ? 'active' : ''}" data-date="${formatDate(d)}" onclick="selectDate('${formatDate(d)}', this)">
      <span class="dow">${d.toLocaleDateString('en-US', { weekday: 'short' })}</span>
      ${d.getDate()} ${d.toLocaleDateString('en-US', { month: 'short' })}
    </button>
  `).join('');
  renderTheatres();
}

function formatDate(d) {
  return d.toISOString().slice(0, 10);
}

function selectDate(dateStr, btn) {
  STATE.currentDate = dateStr;
  document.querySelectorAll('.date-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  renderTheatres();
}

function renderTheatres() {
  const el = document.getElementById('theatreList');
  el.innerHTML = THEATRES.map(theatre => `
    <div class="theatre-card">
      <div class="theatre-card-head">
        <div>
          <div class="theatre-name">${theatre}</div>
          <div class="theatre-info">Dolby Atmos • Recliner Available</div>
        </div>
      </div>
      <div class="show-times">
        ${SHOW_TIMES.map(t => `
          <button class="time-pill" onclick="selectShow('${theatre}', '${t}')">${formatTime(t)}</button>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function formatTime(t) {
  const [h, m] = t.split(':').map(Number);
  const period = h >= 12 ? 'PM' : 'AM';
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${String(m).padStart(2, '0')} ${period}`;
}

// ---------------- Seat selection ----------------
async function selectShow(theatre, time) {
  const movie = STATE.currentMovie;
  const showId = buildShowId(movie.movie_id, theatre, STATE.currentDate, time);
  STATE.currentShow = { show_id: showId, theatre, show_date: STATE.currentDate, show_time: time };
  STATE.selectedSeats = [];

  document.getElementById('seatHeader').innerHTML = `
    <h2>${escapeHtml(movie.title)}</h2>
    <p>${theatre} • ${STATE.currentDate} • ${formatTime(time)}</p>
  `;

  showView('seatView');
  await refreshBookedSeats();
  renderSeatMap();
  updateBookingBar();
}

async function refreshBookedSeats() {
  try {
    const data = await apiGet(`/api/seats/${encodeURIComponent(STATE.currentShow.show_id)}`);
    STATE.bookedSeats = data.booked_seats || [];
  } catch (e) {
    console.warn('Could not fetch booked seats, assuming none taken', e);
    STATE.bookedSeats = [];
  }
}

function renderSeatMap() {
  const el = document.getElementById('seatMap');
  el.innerHTML = SEAT_ROWS.map(row => {
    const half = Math.ceil(row.count / 2);
    const seatsHtml = (start, count) => Array.from({ length: count }, (_, i) => {
      const num = start + i + 1;
      const seatId = `${row.label}${num}`;
      const isTaken = STATE.bookedSeats.includes(seatId);
      const isSelected = STATE.selectedSeats.some(s => s.seat_id === seatId);
      const cls = isTaken ? 'taken' : isSelected ? 'selected' : `available ${row.type}`;
      return `<button class="seat ${cls}" data-seat="${seatId}" ${isTaken ? 'disabled' : ''} onclick="toggleSeat('${seatId}', '${row.type}', ${row.price})">${num}</button>`;
    }).join('');

    return `
      <div class="seat-row">
        <span class="row-label">${row.label}</span>
        <div class="seat-group">${seatsHtml(0, half)}</div>
        <div class="seat-aisle"></div>
        <div class="seat-group">${seatsHtml(half, row.count - half)}</div>
        <span class="row-label">${row.label}</span>
      </div>
    `;
  }).join('');
}

function toggleSeat(seatId, type, price) {
  if (STATE.bookedSeats.includes(seatId)) return;
  const idx = STATE.selectedSeats.findIndex(s => s.seat_id === seatId);
  if (idx >= 0) {
    STATE.selectedSeats.splice(idx, 1);
  } else {
    if (STATE.selectedSeats.length >= 10) {
      showToast('You can select up to 10 seats per booking', true);
      return;
    }
    STATE.selectedSeats.push({ seat_id: seatId, seat_type: type, price });
  }
  renderSeatMap();
  updateBookingBar();
}

function updateBookingBar() {
  const count = STATE.selectedSeats.length;
  const total = STATE.selectedSeats.reduce((sum, s) => sum + s.price, 0);
  document.getElementById('selectedCount').textContent = `${count} seat${count !== 1 ? 's' : ''} selected`;
  document.getElementById('selectedPrice').textContent = `₹${total}`;
  document.getElementById('proceedBtn').disabled = count === 0;
}

function backToShowtimes() {
  showView('movieView');
}

// ---------------- Checkout ----------------
function openCheckout() {
  if (STATE.selectedSeats.length === 0) return;
  const total = STATE.selectedSeats.reduce((sum, s) => sum + s.price, 0);
  const seatList = STATE.selectedSeats.map(s => s.seat_id).join(', ');
  document.getElementById('checkoutSummary').innerHTML = `
    <div><span>${escapeHtml(STATE.currentMovie.title)}</span><span>${STATE.currentShow.theatre}</span></div>
    <div><span>${STATE.currentShow.show_date}</span><span>${formatTime(STATE.currentShow.show_time)}</span></div>
    <div><span>Seats</span><span>${seatList}</span></div>
    <div class="total"><span>Total</span><span>₹${total}</span></div>
  `;
  document.getElementById('checkoutModal').classList.remove('hidden');
}

function closeCheckout() {
  document.getElementById('checkoutModal').classList.add('hidden');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('checkoutForm').addEventListener('submit', handleBookingSubmit);
  document.getElementById('searchInput').addEventListener('input', handleSearch);
  loadMovies();
});

function handleSearch(e) {
  const q = e.target.value.trim().toLowerCase();
  const filtered = q
    ? STATE.movies.filter(m => m.title.toLowerCase().includes(q) || m.genre.toLowerCase().includes(q))
    : STATE.movies;
  const el = document.getElementById('movieGrid');
  if (filtered.length === 0) {
    el.innerHTML = `<div class="empty-state" style="grid-column:1/-1">No movies match "${escapeHtml(q)}"</div>`;
    return;
  }
  const original = STATE.movies;
  STATE.movies = filtered;
  renderMovieGrid();
  STATE.movies = original;
}

async function handleBookingSubmit(e) {
  e.preventDefault();
  const name = document.getElementById('custName').value.trim();
  const email = document.getElementById('custEmail').value.trim();
  if (!name || !email) return;

  const submitBtn = e.target.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Booking…';

  const payload = {
    show_id: STATE.currentShow.show_id,
    movie_id: STATE.currentMovie.movie_id,
    movie_title: STATE.currentMovie.title,
    theatre: STATE.currentShow.theatre,
    show_date: STATE.currentShow.show_date,
    show_time: STATE.currentShow.show_time,
    seats: STATE.selectedSeats,
    customer_name: name,
    customer_email: email,
  };

  try {
    const result = await apiPost('/api/book', payload);
    closeCheckout();
    showConfirmation(result);
    try { localStorage.setItem('cinebook_last_email', email); } catch (err) {}
  } catch (err) {
    if (err.status === 409) {
      // Someone else grabbed one of the seats first — exactly the case
      // our DynamoDB conditional write is designed to catch.
      showToast(`Sorry, seat(s) ${err.conflicted_seats?.join(', ') || ''} were just taken. Refreshing seat map…`, true);
      closeCheckout();
      await refreshBookedSeats();
      STATE.selectedSeats = STATE.selectedSeats.filter(s => !(err.conflicted_seats || []).includes(s.seat_id));
      renderSeatMap();
      updateBookingBar();
    } else {
      showToast(err.error || 'Booking failed. Please try again.', true);
    }
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Pay & Book Tickets';
  }
}

function showConfirmation(result) {
  const seatList = result.tickets.map(t => t.seat_id).join(', ');
  const total = result.tickets.reduce((sum, t) => sum + Number(t.price), 0);
  document.getElementById('confirmSub').textContent = `Booking ID ${result.booking_id.slice(0, 8).toUpperCase()}`;
  document.getElementById('ticketStub').innerHTML = `
    <div><span>Movie</span><strong>${escapeHtml(STATE.currentMovie.title)}</strong></div>
    <div><span>Cinema</span><strong>${STATE.currentShow.theatre}</strong></div>
    <div><span>Date &amp; time</span><strong>${STATE.currentShow.show_date}, ${formatTime(STATE.currentShow.show_time)}</strong></div>
    <div><span>Seats</span><strong>${seatList}</strong></div>
    <div><span>Amount paid</span><strong>₹${total}</strong></div>
  `;
  document.getElementById('confirmModal').classList.remove('hidden');
}

function closeConfirm() {
  document.getElementById('confirmModal').classList.add('hidden');
  goHome();
}

// ---------------- My Tickets ----------------
async function showMyTickets() {
  showView('ticketsView');
  const el = document.getElementById('ticketsList');
  el.innerHTML = `<div class="empty-state">Loading your tickets…</div>`;
  try {
    const data = await apiGet('/api/tickets');
    renderTickets(data.tickets || []);
  } catch (e) {
    el.innerHTML = `<div class="empty-state">Couldn't load tickets. Is the API reachable?</div>`;
  }
}

function renderTickets(tickets) {
  const el = document.getElementById('ticketsList');
  if (tickets.length === 0) {
    el.innerHTML = `
      <div class="empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none"><path d="M4 7a2 2 0 012-2h12a2 2 0 012 2v3a2 2 0 000 4v3a2 2 0 01-2 2H6a2 2 0 01-2-2v-3a2 2 0 000-4V7z" stroke="currentColor" stroke-width="1.5"/></svg>
        <div>No tickets booked yet</div>
      </div>`;
    return;
  }
  el.innerHTML = tickets.map(t => `
    <div class="ticket-card" data-show="${escapeHtml(t.show_id)}" data-seat="${escapeHtml(t.seat_id)}">
      <div class="ticket-card-left">
        <div class="ticket-card-title">${escapeHtml(t.movie_title)}</div>
        <div class="ticket-card-meta">${escapeHtml(t.theatre)} • ${t.show_date} • ${formatTime(t.show_time)}</div>
        <div class="ticket-card-seat">Seat ${escapeHtml(t.seat_id)} • ₹${t.price}</div>
      </div>
      <button class="ticket-cancel-btn" onclick="cancelTicket('${escapeHtml(t.show_id)}', '${escapeHtml(t.seat_id)}')">Cancel</button>
    </div>
  `).join('');
}

async function cancelTicket(showId, seatId) {
  try {
    await apiDelete(`/api/tickets/${encodeURIComponent(showId)}/${encodeURIComponent(seatId)}`);
    showToast('Ticket cancelled');
    showMyTickets();
  } catch (e) {
    showToast('Could not cancel ticket', true);
  }
}

function confirmClearAll() {
  if (!confirm('This will permanently delete ALL booked tickets. Continue?')) return;
  clearAllTickets();
}

async function clearAllTickets() {
  try {
    const result = await apiDelete('/api/tickets?confirm=true');
    showToast(`Deleted ${result.deleted_count} ticket(s)`);
    showMyTickets();
  } catch (e) {
    showToast('Could not clear tickets', true);
  }
}
