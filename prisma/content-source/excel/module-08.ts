import type { ModuleSeed } from "@/../prisma/content-source/types";

export const module08: ModuleSeed = {
  slug: "module-08-power-query",
  title: "Power Query",
  description: "Импорт, очистка, объединение и трансформация данных без формул.",
  lessons: [
    {
      slug: "49-import-data",
      title: "Импорт данных",
      description: "Подключение внешних источников через Power Query.",
      objectives: ["Импортировать данные из CSV/внешних источников"],
      theory: `Power Query (Data → Get Data) позволяет подключаться к внешним источникам — CSV, другим книгам Excel, базам данных — и загружать данные без ручного копирования, с возможностью обновления одной кнопкой.`,
      example: `Data → Get Data → From File → From CSV позволяет импортировать таблицу продаж из выгрузки CRM, сохранив связь с исходным файлом для будущих обновлений.`,
      commonMistakes: [
        "Копировать данные вручную вместо настройки обновляемого запроса — тогда придётся повторять работу при каждом обновлении.",
      ],
      exercise: {
        type: "MULTIPLE_CHOICE",
        title: "Импорт через Power Query",
        description:
          "Какое преимущество даёт импорт через Power Query по сравнению с копипастом?",
        difficulty: "BEGINNER",
        points: 15,
        data: {
          type: "MULTIPLE_CHOICE",
          options: [
            "Данные можно обновить одной кнопкой без повторного копирования",
            "Файл становится меньше",
            "Форматирование применяется автоматически",
            "Формулы пересчитываются быстрее",
          ],
        },
        correctAnswer: { type: "MULTIPLE_CHOICE", correctIndices: [0] },
        explanation:
          "Query можно обновлять (Refresh), подтягивая новые данные из источника без ручной работы.",
      },
      quiz: [
        {
          question: "Где находится команда импорта данных в Excel?",
          options: [
            "Вкладка Главная",
            "Вкладка Data → Get Data",
            "Вкладка Вид",
            "Вкладка Рецензирование",
          ],
          correctIndex: 1,
          explanation: "Get Data (Получить данные) находится на вкладке Data.",
        },
      ],
    },
    {
      slug: "50-data-cleaning",
      title: "Очистка данных",
      description: "Приводим сырые данные к рабочему виду.",
      objectives: ["Выполнять базовую очистку данных"],
      theory: `Очистка данных в Power Query включает: удаление лишних пробелов, приведение регистра, замену значений, изменение типов столбцов — всё это фиксируется как шаги запроса и повторяется автоматически при обновлении.`,
      example: `Transform → Format → Trim убирает лишние пробелы сразу во всём столбце, а не в одной ячейке — и это происходит при каждом обновлении данных.`,
      commonMistakes: [
        "Чистить данные вручную в самой таблице вместо шагов Power Query, которые можно повторно применить.",
      ],
      exercise: {
        type: "TRUE_FALSE",
        title: "Шаги очистки",
        description:
          "Шаги очистки данных в Power Query сохраняются и применяются заново при каждом обновлении.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "TRUE_FALSE" },
        correctAnswer: { type: "TRUE_FALSE", value: true },
        explanation:
          "Power Query записывает последовательность шагов (Applied Steps) и повторяет их при Refresh.",
      },
      quiz: [
        {
          question: "Что фиксирует Power Query при выполнении операций очистки?",
          options: [
            "Ничего, изменения одноразовые",
            "Последовательность шагов (Applied Steps)",
            "Только итоговый результат",
            "VBA-код",
          ],
          correctIndex: 1,
          explanation:
            "Каждый шаг сохраняется в списке Applied Steps и может быть переиспользован.",
        },
      ],
    },
    {
      slug: "51-merge-tables",
      title: "Объединение таблиц",
      description: "Merge и Append запросов в Power Query.",
      objectives: ["Различать Merge и Append"],
      theory: `**Merge** объединяет две таблицы по общему ключу «в ширину» (как JOIN в SQL). **Append** склеивает таблицы «в высоту», добавляя строки одной таблицы к другой с одинаковой структурой столбцов.`,
      example: `Merge таблиц «Заказы» и «Клиенты» по столбцу ClientID добавит к заказам данные о клиенте. Append объединит «Продажи за январь» и «Продажи за февраль» в одну таблицу.`,
      commonMistakes: [
        "Использовать Append, когда нужно подтянуть данные по ключу (для этого нужен Merge).",
      ],
      exercise: {
        type: "MULTIPLE_CHOICE",
        title: "Merge или Append",
        description:
          "Нужно объединить таблицы «Продажи за январь» и «Продажи за февраль» с одинаковыми столбцами. Какую операцию использовать?",
        difficulty: "INTERMEDIATE",
        points: 20,
        data: {
          type: "MULTIPLE_CHOICE",
          options: ["Merge", "Append", "Pivot", "Unpivot"],
        },
        correctAnswer: { type: "MULTIPLE_CHOICE", correctIndices: [1] },
        explanation:
          "Append складывает строки таблиц с одинаковой структурой друг под другом.",
      },
      quiz: [
        {
          question: "Merge в Power Query больше всего похож на...",
          options: ["SQL JOIN", "SQL UNION", "Сортировку", "Фильтрацию"],
          correctIndex: 0,
          explanation: "Merge объединяет таблицы по ключу, аналогично JOIN в SQL.",
        },
      ],
    },
    {
      slug: "52-remove-duplicates",
      title: "Удаление дубликатов",
      description: "Находим и убираем повторяющиеся строки.",
      objectives: ["Удалять дубликаты по одному или нескольким столбцам"],
      theory: `Remove Duplicates (в Power Query или на вкладке Data) удаляет строки-дубликаты, оставляя только первое вхождение. Можно указать, по каким столбцам сравнивать строки на дублирование.`,
      example: `Если два заказа имеют одинаковый OrderID из-за ошибки выгрузки, Remove Duplicates по столбцу OrderID оставит только одну из этих строк.`,
      commonMistakes: [
        "Удалять дубликаты по всем столбцам, когда на самом деле дубликатом считается совпадение только по ключевому полю.",
      ],
      exercise: {
        type: "TRUE_FALSE",
        title: "Удаление дубликатов",
        description:
          "При удалении дубликатов Excel всегда сравнивает абсолютно все столбцы таблицы.",
        difficulty: "BEGINNER",
        points: 15,
        data: { type: "TRUE_FALSE" },
        correctAnswer: { type: "TRUE_FALSE", value: false },
        explanation: "Можно выбрать, по каким именно столбцам определять дубликаты.",
      },
      quiz: [
        {
          question: "Какая строка остаётся после удаления дубликатов?",
          options: ["Последняя", "Первая", "Случайная", "Ни одна не остаётся"],
          correctIndex: 1,
          explanation:
            "Excel сохраняет первое вхождение и удаляет последующие дубликаты.",
        },
      ],
    },
    {
      slug: "53-missing-values",
      title: "Работа с пропусками",
      description: "Обработка пустых значений в данных.",
      objectives: ["Обрабатывать пропущенные значения"],
      theory: `Пропуски (пустые ячейки) искажают агрегаты и формулы. Стратегии работы с ними: заполнить значением по умолчанию, заполнить предыдущим известным значением (Fill Down), либо исключить строки с пропусками из анализа — выбор зависит от смысла данных.`,
      example: `В Power Query команда Fill → Down копирует последнее непустое значение вниз по пустым ячейкам столбца — удобно для «вложенных» заголовков в выгрузках.`,
      commonMistakes: [
        "Автоматически заменять все пропуски нулями — для числовых показателей вроде цены это может исказить анализ.",
      ],
      exercise: {
        type: "MULTIPLE_CHOICE",
        title: "Пропуски в данных",
        description:
          "Какая команда Power Query копирует последнее известное значение вниз по пустым ячейкам?",
        difficulty: "INTERMEDIATE",
        points: 15,
        data: {
          type: "MULTIPLE_CHOICE",
          options: ["Fill Down", "Remove Duplicates", "Merge Queries", "Group By"],
        },
        correctAnswer: { type: "MULTIPLE_CHOICE", correctIndices: [0] },
        explanation:
          "Fill Down заполняет пропуски предыдущим непустым значением того же столбца.",
      },
      quiz: [
        {
          question: "Почему нельзя всегда заменять пропуски нулём?",
          options: [
            "Это технически невозможно",
            "Ноль может исказить смысл показателя (например, цены)",
            "Excel запрещает такую замену",
            "Это замедляет пересчёт",
          ],
          correctIndex: 1,
          explanation:
            "Ноль — конкретное значение, которое может быть неверной интерпретацией отсутствия данных.",
        },
      ],
    },
    {
      slug: "54-data-transformation",
      title: "Преобразование данных",
      description: "Смена типов столбцов и другие трансформации в Power Query.",
      objectives: ["Менять тип данных столбца", "Разбивать столбец на несколько"],
      theory: `Power Query позволяет трансформировать структуру данных: менять тип столбца (текст ↔ число ↔ дата), разбивать один столбец на несколько по разделителю, разворачивать/сворачивать таблицы (Pivot/Unpivot).`,
      example: `Split Column → By Delimiter разобьёт столбец «Имя Фамилия» на два отдельных столбца по пробелу — «Имя» и «Фамилия».`,
      commonMistakes: [
        "Менять тип столбца до очистки данных — некорректные значения (пробелы, текст в числовом столбце) превратятся в ошибки.",
      ],
      exercise: {
        type: "MULTIPLE_CHOICE",
        title: "Разделение столбца",
        description:
          "Какая операция Power Query разбивает столбец «Имя Фамилия» на два столбца?",
        difficulty: "INTERMEDIATE",
        points: 15,
        data: {
          type: "MULTIPLE_CHOICE",
          options: [
            "Split Column by Delimiter",
            "Merge Columns",
            "Group By",
            "Change Type",
          ],
        },
        correctAnswer: { type: "MULTIPLE_CHOICE", correctIndices: [0] },
        explanation:
          "Split Column by Delimiter разбивает текст на несколько столбцов по разделителю (например, пробелу).",
      },
      quiz: [
        {
          question: "Что стоит сделать до смены типа столбца на числовой?",
          options: [
            "Ничего специального",
            "Очистить данные от лишних символов и пробелов",
            "Удалить столбец",
            "Отсортировать таблицу",
          ],
          correctIndex: 1,
          explanation:
            "Некорректные символы вызовут ошибки преобразования типа, поэтому сначала нужна очистка.",
        },
      ],
    },
  ],
};
