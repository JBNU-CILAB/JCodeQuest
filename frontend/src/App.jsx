import { useState } from "react";
import "./App.css";
import logo from "./assets/logo.png";

function App() {
  const [page, setPage] = useState("before");

  if (page === "login") {
    return <LoginPage onLogin={() => setPage("after")} />;
  }

  if (page === "after") {
    return (
      <div className="page">
        <header className="header">
          <a href="/" className="logo">
            <img src={logo} alt="logo" />
          </a>

          <nav className="nav">
            <a>공지</a>
            <a>문제페이지</a>
            <a>랭킹</a>
          </nav>

          <div className="profile">
            <div className="profileIcon">👤</div>
            <span>로그아웃/마이페이지</span>
          </div>
        </header>

        <section className="hero">
          <div className="welcomeBox">
            <div className="cat">🐱</div>

            <h1>환영합니다!</h1>

            <h2>로그인 되었습니다💚</h2>

            <p>즐거운 코딩 라이프를 시작해보세요!</p>

            <p>오늘도 좋은 하루 되세요 😊</p>

            <div className="buttons">
              <button className="primary">문제 풀러가기</button>

              <button className="secondary">마이페이지</button>
            </div>
          </div>
        </section>

        <main className="content">
          <div className="cardGrid">
            <RankingCard />

            <WeeklyProblems />
          </div>

          <RecentSubmissions />
        </main>
      </div>
    );
  }

  return <HomeBeforeLogin onGoLogin={() => setPage("login")} />;
}

function HomeBeforeLogin({ onGoLogin }) {
  return (
    <div className="page">
      <header className="header">
        <a href="/" className="logo">
          <img src={logo} alt="logo" />
        </a>
      </header>

      <section className="beforeHero">
        <div className="beforeBox">
          <div className="cat">🐱</div>

          <h1>로그인하고</h1>

          <h1 className="green">문제를 풀어보세요!</h1>

          <p>
            AI 튜터와 함께 실력을 키우고,
            <br />
            랭킹에 도전해보세요.
          </p>

          <div className="buttons">
            <button className="primary" onClick={onGoLogin}>
              로그인
            </button>

            <button className="secondary" onClick={onGoLogin}>
              회원가입
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function LoginPage({ onLogin }) {
  return (
    <div className="page">
      <header className="header">
        <a href="/" className="logo">
          <img src={logo} alt="logo" />
        </a>
      </header>

      <section className="loginPage">
        <div className="loginCard">
          <div className="loginLeft">
            <h2>이메일 로그인</h2>

            <p>가입하신 이메일 주소로 로그인하세요.</p>

            <input type="text" placeholder="이메일" />

            <input type="password" placeholder="비밀번호" />

            <label className="keepLogin">
              <input type="checkbox" defaultChecked />
              로그인상태유지
            </label>

            <button className="orangeBtn" onClick={onLogin}>
              로그인
            </button>

            <div className="loginLinks">
              <span>회원가입</span>

              <span>아이디 · 비밀번호 찾기</span>
            </div>
          </div>

          <div className="loginRight">
            <h2>회원가입!</h2>

            <img src={logo} alt="logo" />

            <p>cd의 새로운 멤버가 되어보세요.</p>

            <button className="orangeBtn" onClick={onLogin}>
              회원가입!
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function RankingCard() {
  const users = [
    ["🥇", "Gaurav Kumar", 678],
    ["🥈", "Chirag Maniar", 675],
    ["🥉", "Lukas T", 675],
    ["4", "C. Kevin Chen", 673],
    ["5", "Jiawei Zhang", 668],
  ];

  return (
    <section className="card">
      <h3>🏆 이번주 랭킹</h3>

      {users.map((user, index) => (
        <div className="rankRow" key={index}>
          <span>{user[0]}</span>

          <div>
            <strong>{user[1]}</strong>

            <p>7 Solved · 7 Day streak</p>
          </div>

          <b>🏆 {user[2]}</b>
        </div>
      ))}
    </section>
  );
}

function WeeklyProblems() {
  const weeks = [
    ["5월 2주차", 50, "문제 풀기"],
    ["5월 1주차", 80, "문제 풀기"],
    ["4월 4주차", 100, "완료"],
  ];

  return (
    <section className="card">
      <div className="cardHeader">
        <h3>📅 주차별 문제</h3>

        <a>전체 보기 ›</a>
      </div>

      {weeks.map((week, index) => (
        <div className="weekRow" key={index}>
          <strong>{week[0]}</strong>

          <div className="progress">
            <div style={{ width: `${week[1]}%` }}></div>
          </div>

          <button>{week[2]}</button>
        </div>
      ))}
    </section>
  );
}

function RecentSubmissions() {
  return (
    <section className="card recent">
      <div className="cardHeader">
        <h3>&lt;/&gt; 최근 제출</h3>

        <a>전체 보기 ›</a>
      </div>

      <table>
        <thead>
          <tr>
            <th>문제</th>
            <th>결과</th>
            <th>메모리</th>
            <th>시간</th>
            <th>언어</th>
            <th>제출 시간</th>
          </tr>
        </thead>

        <tbody>
          <tr>
            <td>Two Sum</td>

            <td className="success">맞았습니다!</td>

            <td>12.4 MB</td>

            <td>124 ms</td>

            <td>Python 3</td>

            <td>2분 전</td>
          </tr>
        </tbody>
      </table>
    </section>
  );
}

export default App;