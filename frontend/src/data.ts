import type { RankUser, Submission, WeeklyProblem } from './types'

export const RANKINGS: RankUser[] = [
  { rank: 1, name: 'Gaurav Kumar', solved: 7, streak: 7, score: 678 },
  { rank: 2, name: 'Chirag Manjar', solved: 7, streak: 7, score: 675 },
  { rank: 3, name: 'Lukas T', solved: 7, streak: 7, score: 675 },
  { rank: 4, name: 'C. Kevin Chen', solved: 6, streak: 5, score: 673 },
  { rank: 5, name: 'Jiawei Zhang', solved: 6, streak: 5, score: 668 },
]

export const WEEKLY_PROBLEMS: WeeklyProblem[] = [
  { label: '5월 2주차', solved: 5, total: 10 },
  { label: '5월 1주차', solved: 8, total: 10 },
  { label: '4월 4주차', solved: 10, total: 10 },
]

export const SUBMISSIONS: Submission[] = [
  {
    problem: 'Two Sum',
    verdict: 'AC',
    verdictLabel: '맞았습니다',
    memory: '12.4 MB',
    time: '124 ms',
    language: 'Python 3',
    submittedAt: '2분 전',
  },
  {
    problem: 'Reverse Linked List',
    verdict: 'WA',
    verdictLabel: '틀렸습니다',
    memory: '13.1 MB',
    time: '96 ms',
    language: 'Python 3',
    submittedAt: '14분 전',
  },
  {
    problem: 'Valid Parentheses',
    verdict: 'AC',
    verdictLabel: '맞았습니다',
    memory: '11.8 MB',
    time: '52 ms',
    language: 'C++17',
    submittedAt: '1시간 전',
  },
]
