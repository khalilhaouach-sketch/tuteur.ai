"""Petit jeu de données d'exemple pour le profil P2 (1AC, arabe).

PROVISOIRE : banque d'exercices d'exemple sur trois leçons du programme de 1AC
(voir docs/programmes/1ac_arabe.md). Les explications viennent de docs/ (lire_programme).
Le contenu ci-dessous doit être relu par le professeur.
"""

# Pour chaque notion : une banque d'exercices.
# Chaque exercice : réponses acceptées, erreurs connues (réponse -> type d'erreur),
# un indice (après une première erreur) et une explication (après la deuxième).
# Les réponses sont entièrement vocalisées : une voyelle écrite par l'élève est toujours vérifiée.
# « voyelles_obligatoires » : la réponse doit être entièrement vocalisée (exercices où le شكل est l'objet).
NOTIONS = {
    "الميزان الصرفي": {
        "niveau": "P2",
        "exercices": [
            {
                "id": "mizan-1",
                "difficulte": 1,
                "voyelles_obligatoires": True,
                "enonce": "ما وزن الفعل «جَلَسَ»؟",
                "reponses": ["فَعَلَ"],
                "erreurs": {"فاعل": "زيادة حرف غير موجود في الكلمة", "جلس": "عدم استعمال الميزان (ف ع ل)"},
                "indice": "يقابل الحرف الأول الفاءَ، والثاني العينَ، والثالث اللامَ.",
                "explication": "وزن «جَلَسَ» هو «فَعَلَ»: الجيم تقابل الفاء، واللام تقابل العين، والسين تقابل اللام.",
            },
            {
                "id": "mizan-2",
                "difficulte": 2,
                "voyelles_obligatoires": True,
                "enonce": "ما وزن الفعل «أَكْرَمَ»؟",
                "reponses": ["أَفْعَلَ"],
                "erreurs": {"فعل": "إغفال الحرف الزائد في الميزان", "افتعل": "خطأ في موضع الحرف الزائد"},
                "indice": "«أَكْرَمَ» فعل مزيد: أصله «كَرُمَ»، والهمزة في أوله زائدة. والزائد يُكتب في الميزان كما هو.",
                "explication": "وزن «أَكْرَمَ» هو «أَفْعَلَ»: الهمزة زائدة نكتبها في الميزان بلفظها، و«ك ر م» تقابل «ف ع ل».",
            },
            {
                "id": "mizan-3",
                "difficulte": 3,
                "voyelles_obligatoires": True,
                "enonce": "ما وزن الفعل «اِسْتَخْرَجَ»؟",
                "reponses": ["اِسْتَفْعَلَ"],
                "erreurs": {"فعل": "إغفال الحروف الزائدة في الميزان", "افتعل": "خطأ في عدد الحروف الزائدة"},
                "indice": "حروفه الأصلية «خ ر ج»، وقد زيدت في أوله ثلاثة أحرف: ا س ت.",
                "explication": "وزن «اِسْتَخْرَجَ» هو «اِسْتَفْعَلَ»: زيدت الألف والسين والتاء، و«خ ر ج» تقابل «ف ع ل».",
            },
        ],
    },
    "إعراب الفعل المضارع": {
        "niveau": "P2",
        "exercices": [
            {
                "id": "mudari3-1",
                "difficulte": 1,
                "enonce": "ما الحرف الذي نصب الفعل المضارع في الجملة: لَنْ يَتَأَخَّرَ التِّلْمِيذُ؟",
                "reponses": ["لَنْ"],
                "erreurs": {"التلميذ": "خلط بين الناصب والفاعل", "يتأخر": "خلط بين الناصب والفعل"},
                "indice": "حرف النصب يأتي قبل الفعل المضارع مباشرة.",
                "explication": "الحرف الناصب هو «لَنْ»، ولذلك جاء الفعل «يَتَأَخَّرَ» منصوبًا وعلامة نصبه الفتحة.",
            },
            {
                "id": "mudari3-2",
                "difficulte": 2,
                "enonce": "ما علامة رفع الفعل المضارع في الجملة: يَدْرُسُ التِّلْمِيذُ؟",
                "reponses": ["الضَّمَّةُ", "الضَّمَّةُ الظَّاهِرَةُ"],
                "erreurs": {"الفتحة": "خلط بين علامة الرفع وعلامة النصب", "السكون": "خلط بين علامة الرفع وعلامة الجزم"},
                "indice": "الفعل لم يسبقه ناصب ولا جازم، فهو مرفوع: انظر إلى حركة آخره.",
                "explication": "«يَدْرُسُ» مرفوع لأنه لم يسبقه ناصب ولا جازم، وعلامة رفعه الضمة الظاهرة على آخره.",
            },
            {
                "id": "mudari3-3",
                "difficulte": 3,
                "enonce": "ما علامة نصب الفعل المضارع في الجملة: التَّلَامِيذُ لَنْ يَتَأَخَّرُوا؟",
                "reponses": ["حَذْفُ النُّونِ", "حَذْفُ النُّونِ لِأَنَّهُ مِنَ الأَفْعَالِ الخَمْسَةِ"],
                "erreurs": {"الفتحة": "إغفال حكم الأفعال الخمسة", "ثبوت النون": "خلط بين علامة الرفع وعلامة النصب في الأفعال الخمسة"},
                "indice": "«يَتَأَخَّرُوا» من الأفعال الخمسة: كيف تُنصب هذه الأفعال؟",
                "explication": "«يَتَأَخَّرُوا» فعل مضارع منصوب بـ«لَنْ»، وعلامة نصبه حذف النون لأنه من الأفعال الخمسة.",
            },
        ],
    },
    "النكرة والمعرفة": {
        "niveau": "P2",
        "exercices": [
            {
                "id": "nakira-1",
                "difficulte": 1,
                "enonce": "هل كلمة «مَدِينَةٌ» نكرة أم معرفة؟",
                "reponses": ["نَكِرَةٌ"],
                "erreurs": {"معرفة": "خلط بين النكرة والمعرفة"},
                "indice": "هل تدل الكلمة على مدينة معيَّنة نعرفها، أم على أيِّ مدينة؟",
                "explication": "«مَدِينَةٌ» نكرة لأنها لا تدل على مدينة معيَّنة، ويدل على ذلك التنوين وغياب «ال».",
            },
            {
                "id": "nakira-2",
                "difficulte": 2,
                "voyelles_obligatoires": True,
                "enonce": "اِجْعَلِ النكرة معرفة بإدخال «ال» عليها: كِتَابٌ",
                "reponses": ["الكِتَابُ"],
                "erreurs": {"كتاب": "عدم إدخال «ال» التعريف", "الكِتَابٌ": "إبقاء التنوين مع «ال» التعريف"},
                "indice": "أضف «ال» في أول الكلمة، وانتبه: المعرَّف بـ«ال» لا يُنوَّن.",
                "explication": "تصير «كِتَابٌ» معرفة بإدخال «ال»: «الكِتَابُ»، ويُحذف التنوين.",
            },
            {
                "id": "nakira-3",
                "difficulte": 3,
                "enonce": "ما نوع المعرفة في كلمة «هَذَا»؟",
                "reponses": ["اِسْمُ إِشَارَةٍ", "اِسْمُ الإِشَارَةِ"],
                "erreurs": {"ضمير": "خلط بين اسم الإشارة والضمير", "اسم موصول": "خلط بين اسم الإشارة والاسم الموصول"},
                "indice": "نستعمل هذه الكلمة لنشير بها إلى شيء قريب.",
                "explication": "«هَذَا» اسم إشارة للمفرد المذكر القريب، وهو من أنواع المعرفة.",
            },
        ],
    },
}

EXERCICES = {ex["id"]: (notion, ex) for notion, d in NOTIONS.items() for ex in d["exercices"]}
