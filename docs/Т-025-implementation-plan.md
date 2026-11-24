# T-025, последна част — реална детайлна прогноза и почасов cloudbase

## Цел, текуща основа и крайно поведение

Свържи `/forecast?site=<slug>&date=YYYY-MM-DD` с публикуваната SQLite прогноза, точните достъпни weather входове, структурираните причини и 11-те почасови cloudbase резултата. ML публикацията и началната страница вече са приети. Използвай съществуващите read-only database connection, избор на публикация, форматери, badges и метаданни от dashboard-а. Изпълнението на този план завършва T-025 след проверка на резултата и приемане от собственика.

Новият изглед има toolbar, по-висок основен ред и графика отдолу. В основния ред главната карта е вляво, а вдясно са **Forecast inputs** и **Why this result**, едно под друго. Премахни картата, стария отделен долен ред с inputs/drivers и целия placeholder **Compared with previous run**. Страницата заема екрана без scroll. Пълното съдържание на многобройните входове и обяснения се достига чрез селектори и страници вътре в панелите.

### Избор, навигация и заявки

- Детайлният endpoint остава `GET /api/v1/forecasts?siteSlug=…&date=…`. В SQLite режима използвай същото класиране като summaries — точна локация и целева дата, после GFS `reference_at_utc DESC`, publication `created_at_utc DESC`, publication ID и prediction ID. Преизползвай текущата selection логика в `SqliteForecastRepository`, така че summary и detail да връщат еднакви outputs и metadata при една и съща база. Късно импортиран стар цикъл не измества по-новия.
- Избери **един prediction ID** преди останалите JOIN-ове. Outputs, weather snapshot, drivers и hours трябва да принадлежат на него. Използвай една кратка read transaction за последователните SQL заявки, за да получиш съгласуван резултат при паралелна ML публикация. Всичко за отговора се чете от SQLite. Пълните ML артефакти остават за replay.
- Публикувана прогноза с липсваща метрика е валидна детайлна страница. Не замествай тази метрика от друг рън. При липса на прогноза за точната дата потърси по-ранните цикли за същата дата чрез същото класиране. При пълна липса върни `404 FORECAST_NOT_FOUND`, при непознат slug — `404 SITE_NOT_FOUND`. Несъгласуван FK, дублиран източник или счупен публикуван максимум е 5xx/contract грешка. Липсваща измерена стойност остава `NULL` с причина.
- Активирай истинските линкове `View detailed forecast` и Other locations от началната страница в SQLite режим за наличните публикации. В `All sites` запази избраните site/date. Toolbar-ът съдържа обратния линк и текущите site/date selectors. Датите са петте позиции `today − 2 … today + 2` от API. Пълна липса на прогноза прави опцията disabled, липсваща P100 при наличен ден оставя опцията активна.
- При директен URL с валидна календарна дата зареди точно нея, включително извън петдневния прозорец. Добави я като текуща опция в detail selector-а. Ако прогнозата липсва, запази поисканата дата и покажи empty state. При липсваща/невалидна дата избери наличния Today, после най-близката бъдеща, после най-близката минала от days. При празен прозорец покажи empty state. Смяната на локация запазва избраната дата и допуска explicit unavailable state за новата локация.
- Използвай съществуващия detail query key по slug/date и проверката за correlation. Приложи ръчната refresh policy от dashboard-а — без polling и refetch при focus/reconnect/mount на вече кеширана заявка. Изричният Retry при retryable мрежова или 5xx грешка повтаря неуспешната заявка. Каталогът, days и detail имат собствени loading/error състояния. При смяна на селекцията старите inputs, drivers и hours не се показват като данни за новата дата. Ръчното презареждане зарежда последната налична публикация.
- Поддържай новата detail форма и в изричен `mock` режим с ясни mock статути. Обнови demo fixtures по новия договор. Данните и графиката в този режим остават синтетични.

## API договор и източници

Промени локално и съгласувано `packages/contracts`, API и web. Изнеси общите dashboard metric/metadata schemas в споделен модул при нужда, за да могат summary и detail да ги преизползват без цикличен import. Замени стария detail договор с неподходящия фиксиран списък mock входове и string array drivers.

Отговорът има `siteId`, `siteSlug`, `forecastDate`, `generatedAt`, `metadata`, `outputs`, `forecastInputs`, `explanations` и `cloudbaseHours`.

- `outputs` и `metadata` използват вече работещата dashboard форма. P100/P200/P300 са проценти в API, с преобразуване от SQLite 0–1 и без предварително закръгляне. Cloudbase използва `estimated|conditional_lcl|blue|other_cloud|indeterminate|missing`. OD запазва nullable score при критичен override. Confidence, status, missing reason и limitations идват от редовете `prediction_metric_details`.
- `forecastInputs` има `windowStartUtc`, `windowEndUtc`, `featureContractVersion`, `xcFeatures` и `hourlyContext`. `xcFeatures` е списък от 67 реда в фиксиран ред, описан по-долу. Всеки ред съдържа `key`, `label`, `group`, `scope`, канонична `unit`, `value: number|null`, `dataStatus`, `qualityState`, `missingReason` при липса, optional `provenanceId`, `statistic` и optional граници на слоя или интервала. Форматирането за потребителя е във web. `hourlyContext` съдържа 11 часа с `validAtUtc`, отделни списъци `odInputs` и `cloudbaseContext` по същата форма. Точните OD интервали запазват и `intervalStartUtc/intervalEndUtc`.
- `explanations` съдържа пет групи по `metricCode: p100|p200|p300|overdevelopment|cloudbase`. Във всяка върни статус и ограничения на метриката плюс `drivers` в записания `rank`, максимум три. Driver редът има записаните `kind`, `code`, `message`, `rank` и приложимите optional `xcStage`, `direction`, `contributionLogit`, `scorePoints`, `supportSuccesses`, `supportTotal`. `inputs` съдържа подредените `inputKey`, UTC час/интервал, optional provenance ID и разрешеното входно поле. Не пресмятай нови приноси и не ранжирай записаните drivers отново.
- `cloudbaseHours` е подреден списък от точно 11 уникални часа 10:00–20:00 в София. Всеки има `validAtUtc`, `regime`, `heightMslM`, `heightModelAglM`, `heightSiteAglM` като число или null, `confidenceLevel`, `reasonCode`, `reasonText` и optional `note`. Източникът е `prediction_cloudbase_hours` за избрания prediction ID. `reasonText` идва от речник за текущите кодове в T-022, с human-readable fallback за непознат код. Пази оригиналния код и бележката в информацията.
- Проверявай strict Zod формите и съгласуваността на стойност, режим и статус. При `cumulus` височините са налични, при `indeterminate` са допустима тройка или всички null, при `blue|other_cloud|missing` са null. Site AGL допуска отрицателна стойност. `missing` изисква null confidence. Сверявай часовете със съответния Sofia ден, включително DST, и дневните maxima с часовете в същия отговор. Публикация със счупен задължителен граф връща грешка, а частично липсваща weather стойност запазва своя missing state.

### SQL връзки и метаданни

- `prediction_runs` предоставя `created_at_utc → generatedAt`, `xc_model_id`, `cloudbase_method_version` и `overdevelopment_policy_version`. `weather_product_runs.reference_at_utc` е GFS cycle, `weather_ingestion_runs.target_local_date` е целевият ден, а разликата между календарните дати е хоризонтът. Преизползвай `fromPreviousIssue` от summary. Съществуващите правила за оперативен 06Z и разрешение за употреба остават критерий за избиране.
- `predictions.daily_feature_snapshot_id` фиксира daily snapshot и двата слоя от `weather_daily_feature_profile_layers`. `weather_daily_feature_snapshot_inputs` свързва точните почасови `weather_point_samples`, а `weather_product_valid_times` дава UTC часовете. Към всяка проба има `weather_point_interval_measurements`, `weather_point_convection_measurements` и `weather_field_provenance`.
- Разрешавай provenance по owning row, `field_code`, `field_variant` и `statistic_type`. Вариантът на поле без специален variant е `canonical`. Същата съпоставка се използва в ML `publication/drivers.py`. Пази quality и reason от конкретния provenance. Налична валидна GFS стойност с `real` или `derived` quality получава публичен badge `Real`. Липсваща, unsupported, sentinel или invalid стойност получава `Unavailable` и причина. Стойност с противоречив provenance е грешка.
- `prediction_drivers` и `prediction_driver_inputs` са единственият източник на публикуваните top drivers. Разреши provenance FK до точния owner и проверявай принадлежност към избрания snapshot или свързаните му samples. При null FK пази името и часа и покажи „Exact input is retained in the ML artifact“, когато няма точен SQL еквивалент. Контекст от друга таблица не се представя като точно същия консумиран вход.
- Изпълни ограничен брой пакетни заявки за избрания prediction. Не прави заявка за всяко отделно поле или driver. През API не се четат raw/interim/prediction файлове, не се стартира Python и не се изчислява модел.

### Forecast inputs — пълен фиксиран XC inventory

Използвай точно 67-те `required_features` от текущата `xc-probability-policy-v1.json` като източник при подготовка на TypeScript mapping-а. SQL имената по-долу са каноничните имена на колоните. Извърши автоматизирана проверка в тестовете за съвпадение на списъка с пакетираната Python policy. Runtime API използва TypeScript mapping-а.

За дневните записи `key = daily.<column>`, owner е избраният `weather_daily_feature_snapshots`. За слоевете prefix-ът е `layer_0_1500.` или `layer_1500_3000.`, owner е редът за точно този слой и snapshot. Запази реда от policy.

| Група в панела | Колони и единици |
| --- | --- |
| Surface temperature | `air_temperature_2m_mean_k`, `air_temperature_2m_min_k`, `air_temperature_2m_max_k`, `dew_point_temperature_2m_mean_k` — K. |
| Humidity | `relative_humidity_2m_mean_percent`, `relative_humidity_2m_max_percent` — %. `total_column_water_vapour_mean_kg_m2` — kg/m². |
| Pressure and convergence | `surface_pressure_mean_pa`, `mean_sea_level_pressure_mean_pa` — Pa. `neighbourhood_pressure_gradient_mean_pa_per_km`, `neighbourhood_pressure_gradient_max_pa_per_km` — Pa/km. `neighbourhood_low_level_divergence_mean_s_inverse`, `neighbourhood_low_level_divergence_min_s_inverse` — 1/s. |
| Surface wind | `wind_u_10m_mean_m_s`, `wind_v_10m_mean_m_s`, `wind_speed_10m_mean_m_s`, `wind_speed_10m_max_m_s` — m/s. `wind_direction_10m_mean_degrees_from_north` — градуси „от север“. |
| Thermal height | `provider_boundary_layer_height_agl_mean_m`, `provider_boundary_layer_height_agl_max_m`, `mixed_layer_lcl_agl_mean_m`, `mixed_layer_lcl_agl_min_m`, `mixed_layer_lcl_agl_max_m`, `pbl_minus_lcl_mean_m`, `pbl_minus_lcl_max_m` — m. Provider PBL и mixed-layer LCL са спрямо моделния терен. |
| Thermal strength and solar radiation | `surface_buoyancy_flux_kinematic_mean_m2_s3`, `surface_buoyancy_flux_kinematic_max_m2_s3` — m²/s³. `convective_velocity_scale_mean_m_s`, `convective_velocity_scale_max_m_s` — m/s. `shortwave_radiation_mean_w_m2`, `shortwave_radiation_max_w_m2`, `surface_sensible_heat_flux_mean_w_m2`, `surface_latent_heat_flux_mean_w_m2` — W/m². |
| Clouds, rain and stability | `total_cloud_cover_mean_percent`, `total_cloud_cover_max_percent`, `low_cloud_cover_mean_percent`, `low_cloud_cover_max_percent`, `mid_cloud_cover_mean_percent`, `high_cloud_cover_mean_percent` — %. `precipitation_total_mm`, `precipitation_max_hourly_mm` — mm. `cape_max_j_per_kg`, `cin_magnitude_max_j_per_kg` — J/kg. |
| Layer 0–1500 m above site — 11 полета | `temperature_lapse_rate_mean_k_per_km`, `temperature_lapse_rate_max_k_per_km` — K/km. `relative_humidity_mean_percent` — %. `specific_humidity_mean_kg_per_kg` — kg/kg. `wind_u_mean_m_s`, `wind_v_mean_m_s`, `wind_speed_mean_m_s`, `wind_speed_max_m_s` — m/s. `wind_direction_mean_degrees_from_north` — градуси. `wind_shear_mean_m_s_per_km`, `wind_shear_max_m_s_per_km` — m/s/km. |
| Layer 1500–3000 m above site — 13 полета | Същите 11 имена за горния слой плюс `vertical_velocity_mean_pa_s`, `vertical_velocity_min_pa_s` — Pa/s. |

В label-а показвай височината, mean/min/max/total и интервала, когато са приложими. Старите общи mock редове се заменят с тези явни полета. Например „Thermal strength“ става „Convective velocity scale, mean/max“, „Boundary-layer wind“ се заменя с точните налични ветрови полета по височина, а „Convergence“ показва числовата divergence и pressure gradient. Provider cloud base и lower-layer omega са изключени от XC inventory и не получават фиктивни стойности.

Web може да преобразува K → °C, Pa → hPa за pressure, kg/kg → g/kg, а K/km → °C/km като числова разлика. Пази wind m/s и pressure gradient Pa/km. Числата в API са пълни, видимите стойности използват до две десетични позиции, а много малките flux/divergence/omega полета — scientific notation с три значещи цифри. ℹ показва пълната канонична стойност, единица, statistic, quality и provenance, без да изисква място в основния ред.

### OD и cloudbase почасови входове

В панела има selector `XC inputs | OD inputs | Cloudbase context`. XC режимът показва дневните 67 полета по групи. OD и cloudbase режимите имат час 10:00–20:00 и се синхронизират с избраната точка на графиката. Изборът на входен час променя само часовия контекст и графичната селекция.

| Поле/контекст | SQL източник и времеви смисъл |
| --- | --- |
| OD rain | `weather_point_interval_measurements.canonical_value` за `precipitation_amount_mm`, accumulation, точен интервал [час, час+1). Пробата е при края на интервала, съгласно съществуващия publisher. Има десет интервала 10:00–20:00. |
| OD CAPE/CIN | `weather_point_convection_measurements.cape_j_per_kg/cin_magnitude_j_per_kg` за surface parcel от каноничния selector и provenance. Съпостави ги с **началния** час на rain интервала. Десет използвани слота. CIN е положителна величина. Не подменяй с други parcel методи или дневни maxima. |
| OD low cloud, RH, wind | `weather_point_samples.low_cloud_cover_percent`, `relative_humidity_2m_percent`, `wind_speed_10m_m_s` за всички 11 часа. При 20:00 rain и CAPE/CIN са означени „Outside OD interval inputs“, а останалите три се показват. |
| Cloudbase surface context | `surface_pressure_pa`, `air_temperature_2m_k`, `specific_humidity_2m_kg_per_kg`, `provider_boundary_layer_height_agl_m`, `low_cloud_cover_percent`, `total_cloud_cover_percent` от същата sample. Използвай canonical field/variant и hourly provenance, както са посочени от `CLOUD_FIELDS` в publisher-а. |
| Cloudbase heating context | Sensible/latent heat flux от `weather_point_interval_measurements`, със записаните component, statistic и истински интервал. При повече от един нееднозначен кандидат покажи missing/ambiguous причина. Не изчислявай нови интервали в API. |
| Профил и LCL | В tooltip показвай публикуваните MSL/model AGL/site AGL от `prediction_cloudbase_hours`. По-старият `weather_point_samples.mixed_layer_lcl_agl_m` е отделен weather feature и може да се вижда само с етикет „Stored weather LCL“. Пълната T-022 моделна колона включва нива под старта и съществува само в ML артефакта. При `input_key = profile` покажи тази причина за недостъпност на точния профил в SQL. Не представяй `weather_point_profile_levels` като пълния консумиран T-022 профил. |

Използвай явен каталог на canonical field/variant/statistic към owner/column, който е съгласуван с ML selectors. Неподдържан ключ получава името от публикацията и обяснение за недостъпния точен SQL еквивалент. Смесени или липсващи входове не стават нулеви стойности. Пълните изходи и причините остават видими при липсващ почасов контекст.

## Представяне на картите, входовете и причините

### Главна карта и метаданни

- Запази сегашния дизайн на главната detail карта — големия P100 показател с progress bar и confidence, както и текущата подредба на отделните карти за cloudbase, P100, P200, P300 и OD. Във всяка отделна карта премести нейния status badge в един header ред **вдясно от съответната SVG иконка**, със същия compact badge стил като на началната страница. Запази останалата структура на detail картите, включително техните стойности, етикети и per-metric confidence. Преизползвай badge компонента и formatters от dashboard-а. Типографията се адаптира към наличното място в новия основен ред.
- Процентите следват вече приетия formatter — до две десетични позиции, положителни под 0.01% като `<0.01%`, нула като `0%`. Височината е в m MSL, а при избран числов резултат добави компактно и site AGL със запазен знак. Ако дневният резултат е conditional, етикетът е `Conditional LCL`. Blue означава липса на подкрепа за локално купесто образуване и не дава използваем thermal top или гаранция за чисто небе.
- Общият Model confidence meter показва **само P100**. Всеки изход има собствен badge, confidence и ограничения в ℹ информацията. Премахни общите data badges от заглавията на summary, inputs, Why this result и графиката. В inputs статусът е на реда, а причините принадлежат на метрика със собствен статус.
- Под главното заглавие покажи кратко „GFS <дата> 06Z · Published <дата и час Sofia>“. Под inputs покажи „GFS <дата> 06Z · 10:00–20:00 Europe/Sofia“, с контекст на дневни/почасови стойности. Под Why this result показвай версията на съответния избран модел или метод. `generatedAt` е publication creation time. Няма отделен измислен updated timestamp.
- Преизползвай `ForecastInformation` с текущата ℹ иконка за пълните metadata и notes. При detail добави snapshot `feature_contract_version`, смисъла на MSL/двата AGL и limitations. Дългият XC model ID е в ℹ. Инфо панелът работи при hover/focus и touch/click, с Escape/outside close. Дългото съдържание се представя на компактни страници в рамките на viewport-а.

### Forecast inputs и Why this result без scroll

- Inputs се отваря по подразбиране на `XC inputs / Surface temperature`. Selector-ът за групите следва таблицата с inventory. Покажи редове с label, стойност/единица и собствен статус. Пагинирай текущата група с Previous/Next и „x–y of n“. Използвай измерената височина на тялото на панела и височината на реда, за да определиш капацитет от 1 до 6 реда. При resize clamp-ни текущата страница. Пълният label и стойност са достъпни чрез ℹ/focus. При смяна на локация/дата върни групата и страницата към default.
- Why this result има пет ясно означени групи `100+ km | 200+ km | 300+ km | OD risk | Cloudbase`. Desktop използва tabs, при тясна ширина — select със същите пет опции. По подразбиране е P100. В избраната група запази записаните до три причини. При недостатъчна височина показвай 1–3 реда на страница с Previous/Next. При липсваща метрика покажи нейната причина и наличните публикувани обяснения. При нула drivers за наличен резултат покажи „No distinct driver was published“. Пълният текст и свързаните входове са достъпни чрез ℹ на реда.
- P100 показва записаните приноси спрямо тренировъчната референция. За P200 пояснението е „Conditional step P(200+ | 100+); final P200 = P100 × conditional estimate“. За P300 показвай публикуваната формула и действителните successes/total. При сегашния модел това е 3/42. Не означавай contribution_logit като процентни пунктове или причинно влияние. Запазвай score_points при OD като точки от score, а при override показвай текста на задействаното правило.
- Всеки driver запазва връзките от `prediction_driver_inputs`. ℹ показва подредените входни имена, exact стойност при валиден provenance FK, единица и истински час/интервал. При група XC се показват всички свързани features на страници в панела. Отсъстващ точен SQL вход показва причината, без да се подменя с подобна стойност.

### Знаци и иконки на драйверите

| Публикувана информация | Иконка и смисъл |
| --- | --- |
| XC `direction = raises` | `+` в `--color-primary` (#27827c), с достъпен текст „Raises the model estimate“. |
| XC `direction = lowers` | `−` в `--color-danger` (#b64b4b), с текст „Lowers the model estimate“. |
| XC `direction = zero` | `=` в `--color-text-secondary`, с текст „No directional contribution“. |
| `pooled_conversion` | `ƒ`/formula icon в sky цвят (#3b82a0), с текст „Pooled conversion“. |
| `od_override` | Warning triangle в danger цвят, с текст „Critical risk rule“. |
| `od_score_component` | Малка gauge icon в warning цвят (#c7861d), с текст „Risk score component“. При нула точки — вторичен текстов цвят. |
| `cloudbase_reason` | ℹ в sky цвят за обяснение. При missing/uncertain код — warning triangle в warning цвят. |

Записаните OD и cloudbase drivers нямат `direction`. За тях не извеждай `+` или `−` от свободния текст. Положителен числов OD принос означава повече риск, затова неговият знак не се представя като благоприятен зелен сигнал. За cloudbase uncertain кодове използвай `missing`, `indeterminate`, `cloud_type_unknown`, `widespread_low_cloud`, `buoyancy_input_missing`, `transition_or_conflicting_evidence` и кодовете за липсващ/невалиден вход от текущия publisher. Неизвестен код получава неутрално ℹ. Иконките винаги имат текстов смисъл за достъпност.

## Почасова графика и grid

### Layout с фиксиран viewport

- Desktop от 70rem нагоре има ред за toolbar и два съдържателни реда в пропорция **70:30** от оставащата височина. Главният ред има колони **1.08:0.92**. В дясната колона inputs и Why this result са две равни по височина секции. Графиката е на цялата ширина отдолу. Това дава по-голям основен ред от сегашните два почти равни реда.
- Под 70rem използвай toolbar, summary, inputs, Why this result и chart последователно, като разпредели оставащата височина **28:20:24:28**. Компактните selectors са select контроли. Inputs/drivers използват описаната пагинация, за да останат четими.
- Цялата страница, включително header-а, заема `100dvh`. Без вертикален или хоризонтален scroll в страницата или секциите. Типографията, padding и gaps използват същия подход с `clamp()` и ширина/височина като при dashboard-а. Използвай `minmax(0, …)`, `min-height: 0` и размери по наличното пространство. Ограничението се постига с подреждане и пагинация, без скриване на важни стойности.
- Премахни detail-specific импорти и състояния за SiteMap/tiles. Началната карта остава функционална. Няма нов API за сравнение с предишен рън.

### Данни, цветове и рисуване

Използвай Recharts за responsive React SVG chart, стандартни DOM controls и съществуващите theme tokens. На 2026-11-25 собственикът одобри миграцията към Recharts след сравнение на библиотеките ([DEC-074](decisions.md#dec-074---use-recharts-for-the-hourly-cloudbase-plot)); това заменя първоначалния избор за собствено SVG чертане без chart зависимост. Останалите изисквания за данни, сегменти, символи и взаимодействия остават в сила.

| Режим | Линия/маркер и фон |
| --- | --- |
| `cumulus` с височина | Плътна линия и кръг в primary #27827c. Под всеки непрекъснат сегмент — вертикален градиент от същия цвят с opacity 0.22 при линията до 0 към основата на plot-а. |
| `indeterminate` с допустим conditional LCL | Прекъсната линия и ромб във warning #c7861d. Под сегментите — същият цвят с opacity 0.12 → 0. В легендата пише `Conditional LCL`. |
| `blue` | Без числова точка. В режимната лента под plot-а sky #3b82a0 и label `Blue`. |
| `other_cloud` | Без числова точка. Неутрален сив #64737a и label `Other cloud`. |
| `indeterminate` без височина | Warning цвят в режимната лента и label `Uncertain`. |
| `missing` | Border цвят #afc3c5, прекъсната/щрихована клетка и label `Unavailable`. |

- X е времето 10:00–20:00 `Europe/Sofia`. Y е `m MSL`. Долната граница е `min(0, floor(minHeight / 500) × 500)`, горната е `max(500, ceil(maxHeight / 500) × 500)`. Използвай линейна скала и 4–6 равномерни ticks. Без числови височини запази часовата/режимната лента и покажи кратко обяснение вместо числова крива.
- Свързвай само **съседни часове от един и същ числов тип**. Прекъсвай линията и градиента при blue, missing, other cloud, неприложим LCL или смяна между estimated и conditional. Единичният числов час има маркер. Градиентът не премоства празни часове. Не рисувай гладка крива с междучасови екстремуми. Показаните линии са линейни отсечки между публикуваните стойности.
- Пази дневния избор на максимум от T-022. При налична estimated база картата показва нейния максимум, дори conditional LCL да е по-висок в друг час. Часът се означава с отличим outline на маркера и текст `Daily maximum` в tooltip. Conditional максимумът е показваният дневен само при липса на estimated часове. Blue часове нямат нулева или теоретична височина на графиката.
- Hover/focus/click/touch върху час отваря tooltip с час, режим, MSL и двете AGL при наличност, confidence, причина, note и кратките стойности от `cloudbaseContext` за същия час. Поддържай избран час и с keyboard Left/Right върху chart control, Home/End за краищата. При кратък viewport покажи компактния tooltip извън clip-а чрез portal. По подразбиране е часът на показвания дневен максимум, иначе първият час. Избраният час синхронизира часовия selector на inputs. При тесен viewport визуално разреди X labels до 10/12/14/16/18/20, а всички 11 позиции остават интерактивни и достъпни.
- Legend описва цветовете, маркерите и прекъснатата conditional линия. Tooltip обяснява, че conditional LCL е условно ниво на кондензация. Значението не разчита само на цвета. Данните са baseline и неоценена термична достижима височина не се изобразява като изчислен thermal top.

## Проверки, документация и комити

### Автоматизирано приемане

- API тестове през действителния endpoint с disposable мигрирана SQLite база за избора на точната публикация, стар/нов цикъл, втори модел, точна локация, 404, nullable метрики и 5xx при счупен граф. Свери detail outputs и metadata със summaries. Тествай точно 67 XC реда, единиците и mapping-а спрямо ML policy, 11 часа и правилните OD интервaли. Покрий FK със и без точен provenance, няколко parcel метода и ambiguous input. API не чете файлове от data артефактите.
- Тестове на договорите за всеки cloudbase дневен/почасов режим, условен LCL извън профила, nulls, отрицателен site AGL, липсващ confidence и максимум на чужд prediction. Проверявай UTC/Sofia и DST на действителните 11 часа.
- Компонентни/route тестове за петте групи drivers, правилните знаци, Q200 пояснението, 300+ подкрепата, OD override и неутрален cloudbase код. Провери празни drivers, липсващ вход, input pagination, selector-и, resize и reset при смяна на прогноза. Провери P100 confidence, запазените голям P100 показател и подредба на detail картите и per-metric badges вдясно от съответните SVG иконки. Проверявай навигацията от dashboard към detail и обратно, директен URL извън days прозореца и disabled missing дати.
- Chart тестове за смесени режими, отделни сегменти/градиенти, един числов час, всички blue, всички missing, conditional-only, estimated максимум под по-висок conditional час и negative site AGL. Покрий tooltip, keyboard, touch и синхронизацията на часа. Всеки режим има различим текст или маркер.
- Browser проверки на 1440×900, 1366×768, 1280×720, 1280×600, 1024×768 и 390×844, плюс 125% текст при 1280×720 и 390×844. Всички панели и навигационни контроли остават в viewport-а, без scroll или отрязване. Сравни `scrollHeight/Width` с `clientHeight/Width` на page и секциите. В SQLite detail липсват map region, tile заявки и previous-run comparison. Използвай детерминистични fixtures с известна дата и всички режими. Запази browser покритието на приетата начална страница.
- Потвърди липсата на автоматични refetch заявки след изчакване/focus/reconnect. Retry при retryable грешка повтаря съответната заявка и заменя error state след успех.

### Реални данни и край на задачата

Собственикът е приел първите две части. При този етап използвай наличните публикации read-only, без ново сваляне или обучение. Към 17 ноември в локалната база има публикации от 14, 16 и 17 ноември 06Z, включително късно импортиран стар цикъл за 17-и. Това позволява проверка на ranking-а. За Vitosha на 17 ноември избраният цикъл е 16 ноември 06Z. Има conditional височини в 12:00, 13:00 и 14:00 Sofia, с максимум около 2062 m MSL в 14:00 и blue часове около тях. Свери действителните числа в SQL преди записване на acceptance резултата, защото owner може да е добавил нова публикация.

Изпълни `npm run test`, `npm run test:browser`, `npm run repo:check`, `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run build` и `git diff --check`. Coverage на database workspace има документиран предходен проблем в handoff-а. Отчитай го отделно, ако пуснеш coverage, и не променяй праговете като част от UI интеграцията.

Обнови API/web/contracts README с новия detail договор, semantics на данните, графиката и ръчното опресняване. Добави приетото решение за SQLite detail представянето в decisions. В handoff запиши реалната проверка, browser размерите, limitations на cloudbase SQL контекста и останалите непроверени случаи. Промени само статуса на T-025 в tasks според реалната верификация и owner acceptance. До приемането остави Review/In Progress според готовността.

### Последователни комити

1. `T-025 expose published forecast details and weather inputs` — общи metrics/metadata схеми, новият detail договор, SQLite adapter и input inventory, mock adapter и API/contract тестове.
2. `T-025 structure forecast explanations and source metadata` — петте driver групи, provenance resolution, знаци, input context, версиите и tests за mapping.
3. `T-025 integrate the detailed forecast layout` — новият grid, запазеният дизайн на главната detail карта с badges вдясно от SVG иконките, input/driver pagination, selectors, navigation и retry състояния.
4. `T-025 chart hourly cloudbase regimes and heights` — SVG графика, сегменти/цветове/градиенти, часови tooltip и свързване с inputs, component и browser тестове.
5. `T-025 verify and document the complete forecast UI` — всички проверки, реален acceptance checkpoint, документация, decisions, handoff и обоснован статус на тикета.
