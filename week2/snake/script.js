(() => {
  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;

  const scoreEl = document.getElementById('score');
  const bestEl = document.getElementById('best');
  const speedEl = document.getElementById('speed');
  const startBtn = document.getElementById('start');
  const restartBtn = document.getElementById('restart');
  const speedRange = document.getElementById('speedRange');

  // 基础网格：20px 一个格子，400x400 画布 => 20x20 网格
  const GRID = 20;
  const COLS = canvas.width / GRID;
  const ROWS = canvas.height / GRID;

  let snake = [];
  let dir = { x: 1, y: 0 };
  let nextDir = { x: 1, y: 0 };
  let canTurn = true; // 每个 tick 只允许一次转向
  let food = { x: 10, y: 10 };
  let score = 0;
  let best = 0;

  let running = false;
  let timerId = null;
  let fps = 10; // 默认 10 FPS

  // 初始化最高分
  best = parseInt(localStorage.getItem('snake_best') || '0', 10);
  bestEl.textContent = best.toString();

  function initGame() {
    snake = [{ x: 8, y: 10 }, { x: 7, y: 10 }, { x: 6, y: 10 }];
    dir = { x: 1, y: 0 };
    nextDir = { x: 1, y: 0 };
    canTurn = true;
    score = 0;
    scoreEl.textContent = score.toString();
    food = randomFood();
  }

  function randomFood() {
    while (true) {
      const p = {
        x: Math.floor(Math.random() * COLS),
        y: Math.floor(Math.random() * ROWS),
      };
      if (!snake.some(s => s.x === p.x && s.y === p.y)) return p;
    }
  }

  function draw(isGameOver = false) {
    // 背景
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // 细网格
    ctx.strokeStyle = '#eef2f7';
    ctx.lineWidth = 1;
    for (let x = GRID; x < canvas.width; x += GRID) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
    }
    for (let y = GRID; y < canvas.height; y += GRID) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(canvas.width, y);
      ctx.stroke();
    }

    // 食物
    ctx.fillStyle = '#f59e0b';
    roundRectFill(food.x * GRID, food.y * GRID, GRID, GRID, 4);

    // 蛇
    for (let i = 0; i < snake.length; i++) {
      ctx.fillStyle = i === 0 ? '#10b981' : '#34d399';
      roundRectFill(snake[i].x * GRID, snake[i].y * GRID, GRID, GRID, 4);
    }

    if (isGameOver) {
      ctx.fillStyle = 'rgba(0,0,0,0.45)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      ctx.font = 'bold 28px system-ui, -apple-system, Segoe UI, Roboto, Arial';
      ctx.fillText('游戏结束', canvas.width / 2, canvas.height / 2 - 8);
      ctx.font = '16px system-ui, -apple-system, Segoe UI, Roboto, Arial';
      ctx.fillText('按 R 重新开始，或点击开始', canvas.width / 2, canvas.height / 2 + 18);
    }
  }

  function roundRectFill(x, y, w, h, r) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.arcTo(x + w, y, x + w, y + h, rr);
    ctx.arcTo(x + w, y + h, x, y + h, rr);
    ctx.arcTo(x, y + h, x, y, rr);
    ctx.arcTo(x, y, x + w, y, rr);
    ctx.closePath();
    ctx.fill();
  }

  function setFpsFromSlider() {
    fps = parseInt(speedRange.value, 10);
    const mult = (fps / 10).toFixed(1);
    speedEl.textContent = mult + 'x';
    if (running) {
      stopLoop();
      startLoop();
    }
  }

  function startLoop() {
    if (running) return;
    running = true;
    startBtn.textContent = '暂停 (Space)';
    timerId = setInterval(tick, 1000 / fps);
  }

  function stopLoop() {
    running = false;
    startBtn.textContent = '开始 (Space)';
    if (timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  }

  function toggleStart() {
    if (running) stopLoop();
    else startLoop();
  }

  function restart() {
    stopLoop();
    initGame();
    draw(false);
  }

  function tick() {
    // 每帧允许一次转向
    canTurn = true;

    // 应用下一个方向
    dir = nextDir;

    const head = { x: snake[0].x + dir.x, y: snake[0].y + dir.y };

    // 碰撞检测：墙壁或自身
    const hitWall = head.x < 0 || head.x >= COLS || head.y < 0 || head.y >= ROWS;
    const hitSelf = snake.some(seg => seg.x === head.x && seg.y === head.y);
    if (hitWall || hitSelf) {
      return gameOver();
    }

    // 前进
    snake.unshift(head);

    // 吃到食物
    if (head.x === food.x && head.y === food.y) {
      score += 1;
      scoreEl.textContent = score.toString();
      food = randomFood();
    } else {
      // 普通移动，移除尾巴
      snake.pop();
    }

    draw(false);
  }

  function gameOver() {
    stopLoop();
    if (score > best) {
      best = score;
      bestEl.textContent = best.toString();
      localStorage.setItem('snake_best', String(best));
    }
    draw(true);
  }

  function setDirection(x, y) {
    if (!canTurn) return;
    // 禁止直接反向
    if (x === -dir.x && y === -dir.y) return;
    // 禁止重复同方向
    if (x === dir.x && y === dir.y) return;
    nextDir = { x, y };
    canTurn = false;
  }

  // 键盘控制
  document.addEventListener('keydown', (e) => {
    const k = e.key;
    if (k === 'ArrowUp' || k === 'w' || k === 'W') {
      e.preventDefault();
      setDirection(0, -1);
    } else if (k === 'ArrowDown' || k === 's' || k === 'S') {
      e.preventDefault();
      setDirection(0, 1);
    } else if (k === 'ArrowLeft' || k === 'a' || k === 'A') {
      e.preventDefault();
      setDirection(-1, 0);
    } else if (k === 'ArrowRight' || k === 'd' || k === 'D') {
      e.preventDefault();
      setDirection(1, 0);
    } else if (k === ' ' || k === 'Spacebar') {
      e.preventDefault();
      toggleStart();
    } else if (k === 'r' || k === 'R') {
      e.preventDefault();
      restart();
      startLoop();
    }
  });

  // 触摸滑动控制（移动端）
  let touchStartX = 0, touchStartY = 0, touchHandled = false;
  canvas.addEventListener('touchstart', (e) => {
    if (e.touches && e.touches[0]) {
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchHandled = false;
    }
  }, { passive: true });

  canvas.addEventListener('touchmove', (e) => {
    if (!e.touches || !e.touches[0] || touchHandled) return;
    const dx = e.touches[0].clientX - touchStartX;
    const dy = e.touches[0].clientY - touchStartY;
    const adx = Math.abs(dx), ady = Math.abs(dy);
    const threshold = 18;
    if (adx < threshold && ady < threshold) return;

    if (adx > ady) {
      setDirection(dx > 0 ? 1 : -1, 0);
    } else {
      setDirection(0, dy > 0 ? 1 : -1);
    }
    touchHandled = true;
  }, { passive: true });

  // 按钮与滑条
  startBtn.addEventListener('click', toggleStart);
  restartBtn.addEventListener('click', () => {
    restart();
    startLoop();
  });
  speedRange.addEventListener('input', setFpsFromSlider);

  // 失焦自动暂停，避免切出页面蛇继续跑
  window.addEventListener('blur', () => {
    if (running) stopLoop();
  });

  // 初始化
  setFpsFromSlider();
  initGame();
  draw(false);
})();