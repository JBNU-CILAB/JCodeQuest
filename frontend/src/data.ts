import type { Submission, WeeklyProblem } from './types'

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
