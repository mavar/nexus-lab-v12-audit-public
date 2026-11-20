import type { components } from "./api";

export type Model = NonNullable<components["schemas"]["LearnInput"]["model"]>;
export type Axis = components["schemas"]["SearchAxis"];
export type Key = "targetPct"|"dipPct"|"holdSeconds"|"stopPct"|"complexity"|"confidencePct"|"volumeSeconds";
export type Ranges = Record<Key,Axis>;
type Field = {key:Key;label:string;min:number;max:number;step:number;hint:string};

export const MODELS={logistic:"Логистическая модель",tree:"Небольшое дерево",bayes:"Наивный Байес"};
export const START_HINT="Начни со 100 USDT. В тесте на сделку идёт весь свободный баланс. Для покупки нужно от 1 USDT плюс комиссия.";
export const POINTS_HINT="Сколько чисел проверить. От 30 до 120 с двумя точками проверятся 30 и 120. С тремя — 30, 75 и 120. Начни с 2: больше точек — дольше поиск. Чтобы проверить одно число, поставь его в оба поля и укажи 1.";

export function fields(model:Model):Field[]{
  const complexity:Field=model==="tree"
    ?{key:"complexity",label:"Глубина дерева",min:2,max:6,step:1,hint:"От 2 до 6, целое число. Начни с 3. Больше число — больше правил. Слишком много правил может помочь только на знакомых данных."}
    :model==="bayes"
    ?{key:"complexity",label:"Сглаживание Байеса",min:.01,max:10,step:.01,hint:"От 0,01 до 10. Начни с 1. Чем больше число, тем меньше модель доверяет крошечным отличиям в данных."}
    :{key:"complexity",label:"Гибкость модели (C)",min:.01,max:10,step:.01,hint:"От 0,01 до 10. Начни с 1. Меньше число — модель сильнее упрощает правила. Больше — легче подстраивается под старые примеры."};
  return [
    {key:"targetPct",label:"Цель чистыми, %",min:.001,max:5,step:.001,hint:"От 0,001 до 5%. Для первых тестов попробуй 0,10%. Это сколько хотим заработать после расходов. Чем выше цель, тем меньше удачных примеров для обучения."},
    {key:"dipPct",label:"Предел движения против сделки, %",min:0,max:2,step:.001,hint:"От 0 до 2%. Для первого теста попробуй 0,05%. Это сколько цена может пройти против нас: вниз в лонге, вверх в шорте. Меньше число — раньше выход."},
    {key:"holdSeconds",label:"Ждать выхода до, сек",min:15,max:21600,step:1,hint:"От 15 секунд до 6 часов. Начни со 120 секунд. Если время вышло, даём команду закрыть сделку."},
    complexity,
    {key:"confidencePct",label:"Оценка для входа от, %",min:.01,max:99.99,step:.01,hint:"От 0,01 до 99,99%. Для первого теста попробуй 20%. Если оценка модели ниже, она пропускает вход. Больше число — меньше входов."},
    {key:"stopPct",label:"Стоп по чистому убытку, %",min:.001,max:10,step:.001,hint:"От 0,001 до 10%. Для первого теста попробуй 0,2%. При таком убытке после расходов даём команду закрыть сделку. Пока команда идёт, цена может поменяться."},
    {key:"volumeSeconds",label:"Смотреть объём за, сек",min:0,max:3600,step:1,hint:"Попробуй 30 и 120 секунд. За это время считаем сделки и ищем цену, где наторговали больше всего. Короткое окно быстрее замечает перемены. 0 выключает объём для сравнения."},
  ];
}

export function defaults(model:Model):Ranges{
  return {
    targetPct:{lower:.10,upper:.15,points:2},dipPct:{lower:.05,upper:.08,points:2},holdSeconds:{lower:120,upper:240,points:2},
    complexity:{lower:model==="tree"?3:1,upper:model==="tree"?4:2,points:2},
    confidencePct:{lower:10,upper:30,points:3},stopPct:{lower:.15,upper:.25,points:2},
    volumeSeconds:{lower:0,upper:120,points:3},
  };
}

export function axisValues(row:Field,{lower:a,upper:b,points:n}:Axis){
  if(![a,b,n].every(Number.isFinite)||!Number.isInteger(n)||n<1||n>6||a<row.min||b>row.max||b<a||(a===b)!==(n===1))return [];
  const scale=row.step===1?1:1_000_000;
  if(scale===1&&(!Number.isInteger(a)||!Number.isInteger(b)))return [];
  return [...new Set(Array.from({length:n},(_,i)=>Math.round((a+(b-a)*i/Math.max(1,n-1))*scale)/scale))];
}
