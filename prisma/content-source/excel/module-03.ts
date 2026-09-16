import type { ModuleSeed } from "@/../prisma/content-source/types";

const table = {
  headers: ["Клиент", "Регион", "Продажи"],
  rows: [
    ["Alpha", "North", 120000],
    ["Beta", "South", 45000],
    ["Gamma", "North", 210000],
    ["Delta", "South", 98000],
  ],
};

export const module03: ModuleSeed = {
  slug: "module-03-conditional-functions",
  title: "Conditional Functions",
  description: "СУММЕСЛИ, СУММЕСЛИМН, СЧЁТЕСЛИ, СЧЁТЕСЛИМН, СРЗНАЧЕСЛИ, СРЗНАЧЕСЛИМН.",
  lessons: [
    {
      slug: "19-sumif",
      title: "СУММЕСЛИ",
      description: "Суммирует значения, соответствующие одному условию.",
      objectives: ["Суммировать по одному условию"],
      theory: `\`СУММЕСЛИ\` складывает значения из диапазона суммирования только для строк, где диапазон условия соответствует критерию.

\`\`\`excel
=СУММЕСЛИ(диапазон_условия; критерий; диапазон_суммирования)
\`\`\`
`,
      example: `\`\`\`excel
=СУММЕСЛИ(B2:B5;"North";C2:C5)
\`\`\`

Суммирует продажи только клиентов из региона North.`,
      commonMistakes: ["Перепутать порядок диапазонов условия и суммирования."],
      exercise: {
        type: "FORMULA_INPUT",
        title: "Продажи региона North",
        description: "Посчитай сумму продаж только по клиентам из региона North.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "FORMULA_INPUT", table, targetCell: "D1" },
        correctAnswer: {
          type: "FORMULA_INPUT",
          acceptedFormulas: ['=СУММЕСЛИ(B2:B5;"North";C2:C5)'],
          expectedResult: 330000,
        },
        explanation: "Alpha (120000) + Gamma (210000) = 330000.",
      },
      quiz: [
        {
          question: "Сколько условий поддерживает СУММЕСЛИ?",
          options: ["Только одно", "До двух", "Неограниченно", "Ровно три"],
          correctIndex: 0,
          explanation:
            "СУММЕСЛИ работает с одним условием; для нескольких нужна СУММЕСЛИМН.",
        },
      ],
    },
    {
      slug: "20-sumifs",
      title: "СУММЕСЛИМН",
      description: "Суммирует значения по нескольким условиям одновременно.",
      objectives: ["Суммировать по нескольким условиям"],
      theory: `\`СУММЕСЛИМН\` — версия СУММЕСЛИ для нескольких условий. Порядок аргументов отличается: диапазон суммирования указывается первым.

\`\`\`excel
=СУММЕСЛИМН(диапазон_суммы; диапазон_усл1; крит1; диапазон_усл2; крит2; ...)
\`\`\`
`,
      example: `\`\`\`excel
=СУММЕСЛИМН(C2:C5;B2:B5;"North";C2:C5;">100000")
\`\`\`

Сумма продаж North-клиентов, у которых продажи больше 100000.`,
      commonMistakes: [
        "Путать порядок аргументов с СУММЕСЛИ — в СУММЕСЛИМН диапазон суммы идёт первым.",
      ],
      exercise: {
        type: "FORMULA_INPUT",
        title: "North и продажи выше 100000",
        description: "Посчитай сумму продаж клиентов из North с продажами больше 100000.",
        difficulty: "ADVANCED",
        points: 25,
        data: { type: "FORMULA_INPUT", table, targetCell: "D1" },
        correctAnswer: {
          type: "FORMULA_INPUT",
          acceptedFormulas: ['=СУММЕСЛИМН(C2:C5;B2:B5;"North";C2:C5;">100000")'],
          expectedResult: 330000,
        },
        explanation:
          "Both North clients (Alpha 120000, Gamma 210000) exceed 100000, so the sum is 330000.",
      },
      quiz: [
        {
          question: "В СУММЕСЛИМН первым аргументом указывается...",
          options: [
            "Первое условие",
            "Диапазон суммирования",
            "Критерий",
            "Диапазон условия",
          ],
          correctIndex: 1,
          explanation:
            "В отличие от СУММЕСЛИ, СУММЕСЛИМН начинается с диапазона, который нужно просуммировать.",
        },
      ],
    },
    {
      slug: "21-countif",
      title: "СЧЁТЕСЛИ",
      description: "Считает количество ячеек, соответствующих условию.",
      objectives: ["Считать количество по условию"],
      theory: `\`СЧЁТЕСЛИ\` считает, сколько ячеек в диапазоне удовлетворяют критерию.

\`\`\`excel
=СЧЁТЕСЛИ(диапазон; критерий)
\`\`\`
`,
      example: `\`\`\`excel
=СЧЁТЕСЛИ(B2:B5;"North")
\`\`\`

Вернёт количество клиентов из региона North.`,
      commonMistakes: ["Забывать кавычки вокруг текстового критерия."],
      exercise: {
        type: "FORMULA_INPUT",
        title: "Количество клиентов North",
        description: "Посчитай, сколько клиентов относятся к региону North.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "FORMULA_INPUT", table, targetCell: "D1" },
        correctAnswer: {
          type: "FORMULA_INPUT",
          acceptedFormulas: ['=СЧЁТЕСЛИ(B2:B5;"North")'],
          expectedResult: 2,
        },
        explanation: "Alpha и Gamma относятся к North — итого 2.",
      },
      quiz: [
        {
          question: 'СЧЁТЕСЛИ(B2:B5;">100000") посчитает...',
          options: [
            "Сумму значений больше 100000",
            "Количество ячеек со значением больше 100000",
            "Среднее значений больше 100000",
            "Максимум диапазона",
          ],
          correctIndex: 1,
          explanation:
            "СЧЁТЕСЛИ считает количество ячеек, соответствующих условию, а не их сумму.",
        },
      ],
    },
    {
      slug: "22-countifs",
      title: "СЧЁТЕСЛИМН",
      description: "Считает ячейки, соответствующие нескольким условиям.",
      objectives: ["Считать количество по нескольким условиям"],
      theory: `\`СЧЁТЕСЛИМН\` расширяет СЧЁТЕСЛИ на несколько условий сразу, по разным диапазонам.

\`\`\`excel
=СЧЁТЕСЛИМН(диапазон1; крит1; диапазон2; крит2; ...)
\`\`\`
`,
      example: `\`\`\`excel
=СЧЁТЕСЛИМН(B2:B5;"North";C2:C5;">100000")
\`\`\`

Считает клиентов North с продажами выше 100000.`,
      commonMistakes: [
        "Указывать диапазоны разной длины для разных условий — Excel вернёт ошибку.",
      ],
      exercise: {
        type: "FORMULA_INPUT",
        title: "North с высокими продажами",
        description: "Посчитай количество клиентов North с продажами больше 100000.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "FORMULA_INPUT", table, targetCell: "D1" },
        correctAnswer: {
          type: "FORMULA_INPUT",
          acceptedFormulas: ['=СЧЁТЕСЛИМН(B2:B5;"North";C2:C5;">100000")'],
          expectedResult: 2,
        },
        explanation: "И Alpha, и Gamma — из North и превышают 100000 по продажам.",
      },
      quiz: [
        {
          question: "Диапазоны в СЧЁТЕСЛИМН должны быть...",
          options: [
            "Одного размера",
            "Разного размера",
            "Не более двух",
            "Только числовыми",
          ],
          correctIndex: 0,
          explanation: "Все диапазоны условий в СЧЁТЕСЛИМН должны совпадать по размеру.",
        },
      ],
    },
    {
      slug: "23-averageif",
      title: "СРЗНАЧЕСЛИ",
      description: "Среднее значение по одному условию.",
      objectives: ["Считать среднее по условию"],
      theory: `\`СРЗНАЧЕСЛИ\` считает среднее арифметическое значений, соответствующих одному критерию.

\`\`\`excel
=СРЗНАЧЕСЛИ(диапазон_условия; критерий; диапазон_усреднения)
\`\`\`
`,
      example: `\`\`\`excel
=СРЗНАЧЕСЛИ(B2:B5;"North";C2:C5)
\`\`\`

Среднее продаж клиентов North.`,
      commonMistakes: [
        "Забывать третий аргумент, если диапазон условия и диапазон усреднения различаются.",
      ],
      exercise: {
        type: "FORMULA_INPUT",
        title: "Средние продажи North",
        description: "Посчитай средние продажи клиентов из North.",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: { type: "FORMULA_INPUT", table, targetCell: "D1" },
        correctAnswer: {
          type: "FORMULA_INPUT",
          acceptedFormulas: ['=СРЗНАЧЕСЛИ(B2:B5;"North";C2:C5)'],
          expectedResult: 165000,
        },
        explanation: "(120000+210000)/2 = 165000.",
      },
      quiz: [
        {
          question: "СРЗНАЧЕСЛИ похожа по структуре аргументов на...",
          options: ["СУММЕСЛИМН", "СУММЕСЛИ", "СЧЁТЕСЛИМН", "ИНДЕКС"],
          correctIndex: 1,
          explanation:
            "И СРЗНАЧЕСЛИ, и СУММЕСЛИ принимают диапазон условия, критерий, затем диапазон для расчёта.",
        },
      ],
    },
    {
      slug: "24-averageifs",
      title: "СРЗНАЧЕСЛИМН",
      description: "Среднее значение по нескольким условиям.",
      objectives: ["Считать среднее по нескольким условиям"],
      theory: `\`СРЗНАЧЕСЛИМН\` — версия СРЗНАЧЕСЛИ для нескольких условий; диапазон усреднения указывается первым, как в СУММЕСЛИМН.

\`\`\`excel
=СРЗНАЧЕСЛИМН(диапазон_усреднения; диапазон_усл1; крит1; ...)
\`\`\`
`,
      example: `\`\`\`excel
=СРЗНАЧЕСЛИМН(C2:C5;B2:B5;"North";C2:C5;">100000")
\`\`\`

Среднее продаж North-клиентов с продажами выше 100000.`,
      commonMistakes: ["Путать порядок аргументов между СРЗНАЧЕСЛИ и СРЗНАЧЕСЛИМН."],
      exercise: {
        type: "FORMULA_INPUT",
        title: "Среднее North с высокими продажами",
        description: "Посчитай средние продажи клиентов North с продажами больше 100000.",
        difficulty: "ADVANCED",
        points: 25,
        data: { type: "FORMULA_INPUT", table, targetCell: "D1" },
        correctAnswer: {
          type: "FORMULA_INPUT",
          acceptedFormulas: ['=СРЗНАЧЕСЛИМН(C2:C5;B2:B5;"North";C2:C5;">100000")'],
          expectedResult: 165000,
        },
        explanation:
          "Оба клиента North (Alpha, Gamma) превышают 100000, их среднее — 165000.",
      },
      quiz: [
        {
          question: "В СРЗНАЧЕСЛИМН первым аргументом идёт...",
          options: [
            "Критерий",
            "Диапазон условия",
            "Диапазон усреднения",
            "Ничего из перечисленного",
          ],
          correctIndex: 2,
          explanation:
            "Как и в СУММЕСЛИМН, сначала указывается диапазон, по которому считается результат.",
        },
      ],
    },
  ],
};
