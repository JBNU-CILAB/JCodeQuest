import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// 각 단계별 설명 (이미지 기반)
const STEPS = [
  "도약 준비", "도약", "공중", "착지", 
  "달리기 1", "달리기 2", "달리기 3", "복귀"
];

const CatLogo = () => {
  const [step, setStep] = useState(0);

  // 자동으로 고양이가 뛰는 애니메이션 효과
  useEffect(() => {
    const timer = setInterval(() => {
      setStep((prev) => (prev + 1) % 8);
    }, 500); // 0.5초마다 동작 변경
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex flex-col items-center justify-center p-8 bg-white rounded-xl shadow-sm">
      <div className="relative w-64 h-40 flex items-center justify-center">
        {/* 고양이 캐릭터 SVG 영역 */}
        <AnimatePresence mode="wait">
          <motion.svg
            key={step}
            viewBox="0 0 200 120"
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 10 }}
            transition={{ duration: 0.2 }}
            className="w-full h-full"
          >
            {/* 고양이 몸체 (점선 스타일) */}
            <path
              d={getCatPath(step)} // 단계별 경로 데이터
              fill="none"
              stroke="#333"
              strokeWidth="2"
              strokeDasharray="4 4" // 이미지 특유의 점선 효과
              strokeLinecap="round"
            />
            {/* 눈/코 (단순화된 형태) */}
            <circle cx="140" cy="45" r="3" fill="#333" />
            <circle cx="155" cy="45" r="3" fill="#333" />
            
            {/* 바닥 풀밭 표현 */}
            <path
              d="M10,110 L190,110"
              stroke="#4A7c44"
              strokeWidth="1"
              strokeDasharray="2 2"
            />
          </motion.svg>
        </AnimatePresence>
      </div>

      {/* 로고 텍스트 */}
      <div className="mt-4 text-center">
        <h1 className="text-3xl font-bold tracking-widest text-gray-800" 
            style={{ fontFamily: 'monospace', borderBottom: '2px dashed #ccc' }}>
          JCodeQuest
        </h1>
        <p className="text-sm text-green-600 mt-2 font-medium">
          Step {step + 1}: {STEPS[step]}
        </p>
      </div>
    </div>
  );
};

// 단계별 고양이 포즈(SVG Path)를 반환하는 함수 (간략화된 예시 데이터)
function getCatPath(step: number) {
  const paths = [
    "M40,80 Q60,70 90,85 T140,75", // 1. 도약 준비
    "M30,70 Q70,40 120,50 T160,60", // 2. 도약
    "M50,40 Q90,20 130,30 T170,50", // 3. 공중
    "M60,70 Q100,90 140,100 T180,95", // 4. 착지
    "M40,85 Q80,75 120,85 T160,80", // 5. 달리기 1
    "M45,80 Q85,70 125,80 T165,75", // 6. 달리기 2
    "M50,75 Q90,65 130,75 T170,70", // 7. 달리기 3
    "M40,80 Q70,80 100,85 T140,80", // 8. 복귀
  ];
  return paths[step];
}

export function CatGroup() {
  return (
    <>
      {/* 몸체 */}
      <path
        d="M40,80 Q60,70 90,85 T140,75"
        fill="none"
        stroke="#333"
        strokeWidth="2"
        strokeDasharray="4 4"
        strokeLinecap="round"
      />
      {/* 눈 */}
      <circle cx="140" cy="45" r="3" fill="#333" />
      <circle cx="155" cy="45" r="3" fill="#333" />
    </>
  );
}

export default CatLogo;