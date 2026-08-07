// +------------------------------------------------------------------+
// | Nyao Scalper v43.0                                               |
// | Indicator-Based Signal Strength EA with Comprehensive Features   |
// | © Copyright Nyao Scalper by Elriz Wiraswara                      |
// +------------------------------------------------------------------+
#property copyright "© Copyright Nyao Scalper by Elriz Wiraswara"
#property version "43.0"
#property description "Auto Trading EA Robot with Comprehensive Features"
#property description ""
#property description "This is an open-source project for educational and experimental purposes only"
#property description "Source: https://github.com/elrizwiraswara/nyao_scalper_mt5 [BSD-3-Clause]"
#property description ""
#property description "No guarantee of profitability. Use at your own risk. Past performance ≠ future results"
#property description "Built with significant effort, please use and share respectfully"
#property description "I do not sell this EA myself. If sold under my name, treat it as a scam and report it"
#property description "Named after my cat MaoMao, he says 'Nyao!' when spotting good trades"
#property strict

// Windows API for Algo Trading Button Control
#define MT_WMCMD_EXPERTS 32851
#define WM_COMMAND 0x0111
#define GA_ROOT 2
#include <WinAPI\winapi.mqh>

// Dialog Controls for Password Input
#include <Controls\Dialog.mqh>
#include <Controls\Edit.mqh>
#include <Controls\Button.mqh>
#include <Controls\Label.mqh>

// Print wrapper with logging control
#define LogPrint if(EnableLogging) Print

enum ENUM_INPUT_TYPE
{
    INPUT_DOLLAR,                                         // Dollar Amount
    INPUT_PERCENT,                                        // Percent of Equity
    INPUT_POINTS                                          // Points
};

enum ENUM_RR_RISK_MODE
{
    RR_RISK_MANUAL,                                      // Manual Distance
    RR_RISK_ATR                                          // Auto (ATR-Based)
};

enum ENUM_LIMIT_ANCHOR
{
    LIMIT_ANCHOR_FIXED_ATR,                              // Fixed ATR Fraction (flat depth)
    LIMIT_ANCHOR_EMA,                                    // Fast EMA
    LIMIT_ANCHOR_SWING,                                  // Swing Level (structure)
    LIMIT_ANCHOR_SMART                                   // Nearer of Swing/EMA (ATR-capped)
};

input group "+-----------------------------------------+"
input group " Nyao Scalper v43.0"
input group " © Copyright Nyao Scalper by Elriz Wiraswara"
input group "+-----------------------------------------+"

// +------------------------------------------------------------------+
// | Input Parameters                                                 |
// +------------------------------------------------------------------+
input group "📊 Indicator Settings"
input int DirectionalBodyLookback = 10;                   // Lookback for directional body analysis
input int EMAFastPeriod = 5;                              // EMA Fast Period
input int EMASlowPeriod = 12;                             // EMA Slow Period
input int SlopeLookback = 3;                              // EMA Slope Lookback Bars (noise reduction)
input int RSIPeriod = 8;                                  // RSI Period
input int ATRPeriod = 8;                                  // ATR Period
input int ATRAvgLookback = 10;                            // ATR Average Lookback
input double MinVolRatioToTrade = 0.6;                    // Min ATR/AvgATR Ratio to Trade (0 = Disabled, blocks dead market)
input int ImpulseLookback = 3;                            // Impulse Lookback
input double ImpulseBoostWeight = 1.0;                    // Impulse Boost Weight
input int SignalSmoothingCandles = 2;                     // Closed Candles for Weighted Average (1-10)
input double CurrentCandleBlend = 0.40;                   // Current Candle Blend Factor (0.0-1.0)
input double VelocityWindow = 2.0;                        // Velocity Window (Score Delta)
input int RSIOverbought = 80;                             // RSI Overbought Level (Max Buy)
input int RSIOversold = 20;                               // RSI Oversold Level (Min Sell)
input int RSIMomentumBuy = 60;                            // RSI Momentum Buy Trigger
input int RSIMomentumSell = 40;                           // RSI Momentum Sell Trigger

input group "⚖️ Score Weight Settings"
input double TrendWeight = 1.5;                           // Trend Alignment Initial Weight
input double SlopeWeight = 1.5;                           // Trend Slope Confirmation Weight
input double MomentumBaseWeight = 1.0;                    // Momentum Base Weight (RSI Sweet Spot)
input double MomentumTriggerWeight = 0.5;                 // Momentum Trigger Weight (RSI Breakout)
input double BodyMomentumWeight = 1.5;                    // Body Momentum Weight
input double ChopScoreHigh = 2.0;                         // Chop Score High (Strong Trend)
input double ChopScoreMed = 1.0;                          // Chop Score Med (Weak Trend)
input double ChopScoreLow = 0.0;                          // Chop Score Low (Chop Risk - no free points)
input double VolatilityScoreHigh = 1.0;                   // Volatility Score High
input double VolatilityScoreLow = 0.0;                    // Volatility Score Low (no free points)
input double PeakScoreWeight = 1.0;                       // Peak Breakout Score Weight
input double WickRejectionWeight = 1.0;                   // Wick Rejection Penalty Weight
input double MinBodyRatio = 1.5;                          // Min Body Ratio for Wick Calculation

input group "📝 Order & Position Settings"
input bool EnableBuyOrders = true;                        // Enable Buy Orders
input bool EnableSellOrders = true;                       // Enable Sell Orders
input bool EnableNewBarEntryOnly = true;                  // Evaluate/Open Entries Only on New Bar (stable signals)
input bool EnableMaxSpreadFilter = true;                  // Block New Entries When Spread Too Wide
input double MaxSpreadPoints = 0;                         // Max Spread in Points (0 = Auto: ATR-based)
input double MaxSpreadATRRatio = 0.25;                    // Auto Spread Cap as Fraction of ATR (when MaxSpreadPoints = 0)
input double BaseLotSize = 0.01;                          // Base Lot Size
input int MaxOpenOrders = 8;                              // Max Consecutive Open Orders
input int MaxTradesPerCandle = 1;                         // Max Trades Per Candle (0 = Unlimited)
input double ConsecutiveCandleThresholdBoost = 1.0;       // Signal Threshold Boost Per Consecutive Trading Candle
input int MaxConsecutiveCandleBoosts = 3;                 // Max Consecutive Candle Boosts (0 = Unlimited)
input double ZonePoints = 500;                            // Zone Points to Avoid Duplicate Signals
input double BuyDuplicateMultiplier  = 1.5;               // Min Distance Multiplier to Avoid Duplicate Buy Signals
input double SellDuplicateMultiplier = 1.5;               // Min Distance Multiplier to Avoid Duplicate Sell Signals
input double MinBreakEvenProfit = 0.5;                    // Min Profit to Trigger Break-Even ($ | 0 = Disabled)
input double ProfitThresholdMultiplier = 1.5;             // Threshold Multiplier for Min Break-Even Profit
input double LossThresholdMultiplier = 2.0;               // Threshold Multiplier for Max Break-Even Loss
input double MinBuySignalScore = 4.5;                     // Min Signal Strength Score to Buy (0.0 - 10.0)
input double MinSellSignalScore = 4.5;                    // Min Signal Strength Score to Sell (0.0 - 10.0)

input group "🎯 Limit Entry Settings"
input bool EnableLimitEntry = false;                      // Fresh Entries Use Pending Limit (pullback) Instead of Market
input ENUM_LIMIT_ANCHOR LimitEntryAnchor = LIMIT_ANCHOR_FIXED_ATR; // Pullback Anchor (Smart = nearer of Swing/EMA)
input double LimitEntryATRFraction = 0.25;               // Pullback Depth / ATR Cap as Fraction of ATR (below Ask / above Bid)
input int LimitEntryExpiryBars = 1;                       // Cancel Unfilled Limit After N Bars (0 = no expiry)
input bool LimitEntryCancelOnFlip = true;                 // Cancel Pending When Directional Signal Drops Below Threshold

input group "🛡️ Signal Dampening Settings"
input bool EnableSignalDampening = true;                  // Enable Position-Aware Signal Dampening
input int MaxLosingPositionsSameDir = 2;                  // Max Losing Positions in Same Direction Before Block
input double LosingPosScorePenalty = 1.5;                 // Score Penalty Per Losing Same-Direction Position
input double DrawdownThresholdPct = 3.0;                  // Equity Drawdown % to Raise Signal Threshold
input double DrawdownScoreBoost = 2.0;                    // Extra Score Required During Drawdown
input int ConsecutiveLossesBeforeCooldown = 3;            // Consecutive Losses Before Cooldown Activates
input int ConsecutiveLossCooldownBars = 3;                // Cooldown Duration (Bars) After Threshold Reached

input group "🩺 Loss Management Settings"
input bool EnableLossManagement = true;                   // Enable Adaptive Loss Management
input int MaxHoldingLossPositions = 2;                    // Max Losing Positions to Hold
input double MinHealthScore = 0.40;                       // Min Health Score to Hold Position (0.0 - 1.0)
input double MaxAdverseATR = 1.5;                         // Max Adverse Movement in ATR Multiples
input double HealthTrendWeight = 0.40;                    // Health Weight: Trend Alignment
input double HealthRSIWeight = 0.25;                      // Health Weight: RSI Zone
input double HealthATRWeight = 0.25;                      // Health Weight: Adverse Excursion
input double HealthSwingWeight = 0.10;                    // Health Weight: Swing Level
input double HealthRSIBuyMin = 40.0;                      // Health RSI Min for Buy Position
input double HealthRSISellMax = 60.0;                     // Health RSI Max for Sell Position
input int HealthSwingLookback = 20;                       // Swing Level Lookback Bars
input int HealthGraceBars = 2;                            // Grace Period (Bars Before Health Check)
input bool EnablePartialClose = true;                     // Enable Scaled Partial Close on Signal Decay
input double PartialClose75Pct = 0.25;                    // Close % When Signal Drops to 75% of Initial
input double PartialClose50Pct = 0.50;                    // Close % When Signal Drops to 50% of Initial
input double PartialClose25Pct = 1.00;                    // Close % When Signal Drops to 25% of Initial (Remaining)
input bool EnableHealthSLTightening = true;               // Tighten SL as Health Weakens
input double SLTightenATRMultiplier = 2.0;                // ATR Multiplier for Tightened SL
input double SLTightenMinHealthPct = 0.50;                // Start Tightening Below This Health %
input bool EnableBreakEvenOnSpread = true;                // Lock SL to Entry After Profit > Spread Cost
input double BreakEvenSpreadMultiplier = 1.5;             // Spread Multiplier for Break-Even Lock Trigger
input bool EnableVirtualSLReentry = true;                 // Close at Threshold Then Re-evaluate & Re-enter
input bool ReentryRespectsNewBarGate = false;             // Re-entry Obeys New-Bar Entry Gate (no intrabar re-entry)
input double ReentryMinSignalPct = 0.75;                  // Min % of Entry Signal Required to Re-enter
input bool EnableProfitOffsetSL = true;                   // Tighten SL of Losing Pos by Consecutive Closed Profits
input int ConsecutiveWinsRequired = 3;                    // Min Consecutive Wins Before Offset Applies
input double MinOffsetProfit = 1.0;                       // Min Accumulated Profit ($) to Trigger SL Offset

input group "🔀 Hedge Chain (Rolling Martingale Recovery) Settings"
input bool EnableHedgeChain = true;                       // Enable Hedge Chain (MARTINGALE - high risk)
input double HedgeTriggerATR = 1.5;                       // Adverse Move (ATR) to Start the Chain
input bool HedgeRequireSignal = true;                     // Only Hedge if Reverse Signal Confirms (anti-spike)
input double HedgeMinSignalScore = 4.5;                   // Min Reverse-Direction Score to Open Hedge
input bool HedgeAutoLot = true;                           // Auto-size Hedge Lot to Recover (else Multiplier)
input double HedgeRecoveryATR = 1.0;                      // Favorable Move (ATR) to Recover Within
input double HedgeLotMultiplier = 2.0;                    // Fixed Hedge Lot Multiplier (Auto-size OFF)
input double HedgeMaxLot = 0.10;                          // Hard Lot Ceiling Per Hedge Leg
input double HedgeRecoveryPct = 110.0;                    // Close Older Leg When Hedge Covers This % Loss
input double HedgeRollMinProfit = 0.5;                    // Min Older-Leg Profit ($) to Roll
input int HedgeCycleLevels = 2;                           // Max Hedge Levels Per Cycle Before Reseed
input bool EnableHedgeCycleReset = false;                 // Reseed New Cycle at Limit (else Close Chain)
input double HedgeCyclePartialPct = 50.0;                 // % of Deepest Hedge to Close at Reseed
input int HedgeMaxCycles = 3;                             // Max Cycles Before Closing Chain (0 = Unlimited)
input double HedgeMaxChainLossUSD = 0.0;                  // Close Chain if Loss >= this $ (0 = Off)
input double HedgeMaxChainLossPct = 0.0;                  // Close Chain if Loss >= this % Equity (0 = Off)
input bool HedgeClearRootSL = true;                       // Clear First Position SL on Chain Start
input double HedgeTrailATR = 0.5;                         // Graduated Hedge Trail Distance (ATR; 0 = normal trailing)

input group "🧮 Dynamic Lot Sizing Settings"
input bool EnableDynamicLots = true;                      // Enable Dynamic Lot Sizing
input double EquityDropPercent = 5.0;                     // Equity Drop % per Lot Step
input int MaxEquityDropLotSteps = 2;                      // Max Drawdown-Based Lot Steps (0 = Unlimited)
input double MinSignalStrengthForLot = 8.0;               // Min Signal Score for Lot Increase
input double LotStepSize = 0.01;                          // Lot Increase Step Size
input double MaxLotSize = 0.05;                           // Max Lot Size

input group "🏦 Equity Settings"
input bool EnableBasketStop = true;                       // Close All When Total Floating Loss Exceeds Limit
input double MaxBasketLossPct = 8.0;                      // Max Total Floating Loss as % of Equity (0 = Disabled)
input double MinEquityPercent = 70.0;                     // Min Equity % from Peak - Pause Trading when Reached
input double MaxDrawdownFromPeak = 0;                     // Max Equity $ Drawdown - Pause Trading when Reached (0 = Disabled)
input int PauseMinutes = 5;                               // Pause Duration (Minutes)
input double PauseMinutesMultiplier = 1.5;                // Multiply Pause Duration on Each Trigger
input int MaxPauseMinutes = 120;                          // Max Pause Duration Minutes (0 = Max 24,855 days)
input int MaxMinEquityTriggers = 0;                       // Max Times Trigger - Stop Trading when Reached (0 = Unlimited)
input bool ResetOnNewPeak = true;                         // Reset Min Equity Triggers on New Peak Equity
input double TargetEquity = 0;                            // Target Equity - Stop Trading when Reached (0 = Disabled)
input double MinimumEquity = 20;                          // Min Equity - Stop Trading when Reached (0 = Disabled)

input group "📈 Take Profit Settings"
input bool EnableTakeProfit = false;                      // Enable Take Profit
input ENUM_INPUT_TYPE TPInputType = INPUT_DOLLAR;         // TP Input Type
input double TPValue = 10.0;                              // TP Value

input group "📉 Stop Loss Settings"
input bool EnableStopLoss = true;                         // Enable Stop Loss
input ENUM_INPUT_TYPE SLInputType = INPUT_PERCENT;        // SL Input Type
input double SLValue = 10.0;                              // SL Value

input group "⚖️ Risk:Reward Settings"
input bool EnableRiskReward = false;                      // Enable Independent R:R SL/TP (overrides manual SL & TP)
input ENUM_RR_RISK_MODE RRRiskMode = RR_RISK_ATR;         // Risk (SL) Sizing: Manual or Auto ATR
input ENUM_INPUT_TYPE RRRiskInputType = INPUT_POINTS;     // Manual Risk Input Type (when Mode = Manual)
input double RRRiskValue = 200.0;                         // Manual Risk Distance (SL leg, when Mode = Manual)
input double RRAtrMultiplier = 1.5;                       // Auto Risk: SL = ATR × this (when Mode = ATR)
input double RiskRewardRatio = 1.5;                       // Reward : Risk (TP distance = SL distance × this)

input group "💸 Trailing TP/SL Settings"
input bool EnableTrailing = true;                         // Enable Trailing TP/SL
input bool TrailingEnableBreakEvenLock = true;            // Enable Trailing Break-Even Lock
input bool TrailingSLOnProfitableOnly = true;             // Trailing SL on Profitable Position Only
input bool EnableAdaptiveTP = true;                       // Enable Adaptive TP
input bool EnableAdaptiveSL = true;                       // Enable Adaptive SL
input ENUM_INPUT_TYPE TSInputType = INPUT_DOLLAR;         // Trailing Distance Input Type
input double TrailingDistanceValue = 0.2;                 // Trailing Distance Value
input double TrailingValueMultiplier = 0.2;               // Trailing Value Multiplier

input group "🤖 Robot Settings"
input int MagicNumber = 6926268;                          // Magic Number
input bool EnableDiscordAlerts = false;                   // Enable Discord Alerts
input string DiscordWebhookURL = "";                      // Discord Webhook URL
input bool EnableTradingHours = false;                    // Enable Trading Hours
input string TradingStartTime = "00:00";                  // Trading Start Time (HH:MM)
input string TradingEndTime = "23:59";                    // Trading End Time (HH:MM)
input bool EnableReports = true;                          // Enable Trading Reports
input int SendReportEveryHour = 1;                        // Send Report Every (n) Hours 
input bool EnableMarketCloseFilter = true;                // Stop Opening New Positions Near Market Close Hour
input int MinutesBeforeClose = 30;                        // Stop Opening Minutes Before Market Close
input bool EnableNewsFilter = true;                       // Enable News Filter (Pause Trading During News)
input int NewsMinutesBefore = 30;                         // Minutes Before News Event
input int NewsMinutesAfter = 30;                          // Minutes After News Event
input bool EnableLeveragePause = true;                    // Pause Trading When Leverage Changed
input bool EnableLogging = false;                         // Enable EA Logging (May cause lag)

// +------------------------------------------------------------------+
// | Global Variables                                                 |
// +------------------------------------------------------------------+
// EMBEDDED PASSWORD - Change this to your desired password (leave empty to disable)
// const string EA_PASSWORD = "maomao chou kawaii";
const string EA_PASSWORD = "";

// Password Dialog Controls
CDialog passwordDialog;
CEdit passwordEdit;
CButton passwordSubmitBtn;
bool passwordVerified = false;
bool passwordDialogActive = false;

double initialBalance = 0;                                // Initial Account Balance     
double peakEquity = 0;                                    // Peak Equity Recorded
double lastPeakEquity = 0;                                // Last recorded peak equity for drawdown calculations
bool targetEquityReached = false;                         // Flags for target/minimum equity reached
bool minimumEquityReached = false;                        // Flags for target/minimum equity reached
bool minEquityTriggersExceeded = false;                   // Flag when max triggers exceeded
int minEquityTriggerCount = 0;                            // Counter for MinEquityPercent triggers
bool isPaused = false;                                    // Trading pause state
int currentPauseDuration = 0;                             // Current pause duration in minutes
datetime pauseStartTime = 0;                              // Pause start time
bool isOutsideTradingHours = false;                       // Flag when outside trading hours
bool isLeverageDiffFromInitial = false;                   // Flag for leverage changed
bool isNearMarketClose = false;                           // Flag for near market close time
ulong lastProcessedNewsEventID = 0;                       // Last processed news event ID
string symbolBaseCurrency = "";                           // Base currency of the symbol
string symbolQuoteCurrency = "";                          // Quote currency of the symbol
long initialLeverage = 0;                                 // Initial Account Leverage
bool isOrderSendLocked = false;                           // Flag for locking OrderSend execution
bool marketCloseAlertSent = false;                        // Flag for near market close time
bool algoTradingStatus = false; 

//Added by Nobel
// +------------------------------------------------------------------+
// | Atlas Runtime Configuration                                      |
// |                                                                  |
// | Nyao input/.set values remain the startup defaults.              |
// | Atlas will modify these runtime values while the EA is running.  |
// +------------------------------------------------------------------+
struct AtlasRuntimeConfig
{
    // Signal / indicator behavior
    int directionalBodyLookback;
    int emaFastPeriod;
    int emaSlowPeriod;
    int slopeLookback;
    int rsiPeriod;
    int atrPeriod;
    int atrAvgLookback;
    double minVolRatioToTrade;
    int impulseLookback;
    double impulseBoostWeight;
    int signalSmoothingCandles;
    double currentCandleBlend;
    double velocityWindow;
    int rsiOverbought;
    int rsiOversold;
    int rsiMomentumBuy;
    int rsiMomentumSell;

    // Score weights
    double trendWeight;
    double slopeWeight;
    double momentumBaseWeight;
    double momentumTriggerWeight;
    double bodyMomentumWeight;
    double chopScoreHigh;
    double chopScoreMed;
    double chopScoreLow;
    double volatilityScoreHigh;
    double volatilityScoreLow;
    double peakScoreWeight;
    double wickRejectionWeight;
    double minBodyRatio;

    // Entry / execution
    bool enableBuyOrders;
    bool enableSellOrders;
    bool enableNewBarEntryOnly;
    bool enableMaxSpreadFilter;
    double maxSpreadPoints;
    double maxSpreadAtrRatio;
    double baseLotSize;
    int maxOpenOrders;
    int maxTradesPerCandle;
    double consecutiveCandleThresholdBoost;
    int maxConsecutiveCandleBoosts;
    double zonePoints;
    double buyDuplicateMultiplier;
    double sellDuplicateMultiplier;
    double minBreakEvenProfit;
    double profitThresholdMultiplier;
    double lossThresholdMultiplier;
    double minBuySignalScore;
    double minSellSignalScore;

    // Limit entry
    bool enableLimitEntry;
    ENUM_LIMIT_ANCHOR limitEntryAnchor;
    double limitEntryAtrFraction;
    int limitEntryExpiryBars;
    bool limitEntryCancelOnFlip;

    // Signal dampening
    bool enableSignalDampening;
    int maxLosingPositionsSameDir;
    double losingPosScorePenalty;
    double drawdownThresholdPct;
    double drawdownScoreBoost;
    int consecutiveLossesBeforeCooldown;
    int consecutiveLossCooldownBars;

    // Loss / health management
    bool enableLossManagement;
    int maxHoldingLossPositions;
    double minHealthScore;
    double maxAdverseAtr;
    double healthTrendWeight;
    double healthRsiWeight;
    double healthAtrWeight;
    double healthSwingWeight;
    double healthRsiBuyMin;
    double healthRsiSellMax;
    int healthSwingLookback;
    int healthGraceBars;
    bool enablePartialClose;
    double partialClose75Pct;
    double partialClose50Pct;
    double partialClose25Pct;
    bool enableHealthSlTightening;
    double slTightenAtrMultiplier;
    double slTightenMinHealthPct;
    bool enableBreakEvenOnSpread;
    double breakEvenSpreadMultiplier;
    bool enableVirtualSlReentry;
    bool reentryRespectsNewBarGate;
    double reentryMinSignalPct;
    bool enableProfitOffsetSl;
    int consecutiveWinsRequired;
    double minOffsetProfit;

    // Hedge chain
    bool enableHedgeChain;
    double hedgeTriggerAtr;
    bool hedgeRequireSignal;
    double hedgeMinSignalScore;
    bool hedgeAutoLot;
    double hedgeRecoveryAtr;
    double hedgeLotMultiplier;
    double hedgeMaxLot;
    double hedgeRecoveryPct;
    double hedgeRollMinProfit;
    int hedgeCycleLevels;
    bool enableHedgeCycleReset;
    double hedgeCyclePartialPct;
    int hedgeMaxCycles;
    double hedgeMaxChainLossUsd;
    double hedgeMaxChainLossPct;
    bool hedgeClearRootSl;
    double hedgeTrailAtr;

    // Dynamic sizing
    bool enableDynamicLots;
    double equityDropPercent;
    int maxEquityDropLotSteps;
    double minSignalStrengthForLot;
    double lotStepSize;
    double maxLotSize;

    // Equity protection
    bool enableBasketStop;
    double maxBasketLossPct;
    double minEquityPercent;
    double maxDrawdownFromPeak;
    int pauseMinutes;
    double pauseMinutesMultiplier;
    int maxPauseMinutes;
    int maxMinEquityTriggers;
    bool resetOnNewPeak;
    double targetEquity;
    double minimumEquity;

    // TP / SL / risk reward
    bool enableTakeProfit;
    ENUM_INPUT_TYPE tpInputType;
    double tpValue;
    bool enableStopLoss;
    ENUM_INPUT_TYPE slInputType;
    double slValue;
    bool enableRiskReward;
    ENUM_RR_RISK_MODE rrRiskMode;
    ENUM_INPUT_TYPE rrRiskInputType;
    double rrRiskValue;
    double rrAtrMultiplier;
    double riskRewardRatio;

    // Trailing
    bool enableTrailing;
    bool trailingEnableBreakEvenLock;
    bool trailingSlOnProfitableOnly;
    bool enableAdaptiveTp;
    bool enableAdaptiveSl;
    ENUM_INPUT_TYPE tsInputType;
    double trailingDistanceValue;
    double trailingValueMultiplier;

    // Operational filters / diagnostics
    bool enableDiscordAlerts;
    bool enableTradingHours;
    string tradingStartTime;
    string tradingEndTime;
    bool enableReports;
    int sendReportEveryHour;
    bool enableMarketCloseFilter;
    int minutesBeforeClose;
    bool enableNewsFilter;
    int newsMinutesBefore;
    int newsMinutesAfter;
    bool enableLeveragePause;
    bool enableLogging;

};

AtlasRuntimeConfig atlasRuntime;
bool atlasEnabled = true;
bool atlasBuyEnabled = true;
bool atlasSellEnabled = true;

int atlasLastCommandVersion = -1;
string atlasCommandFile = "Atlas\\commands.json";
string atlasStatusFile = "Atlas\\status.json";

bool atlasStructuralConfigDirty = false;
bool atlasHealthWeightsDirty = false;
bool atlasRuntimeInitialized = false;

const double ATLAS_HARD_MAX_LOT = 5.0;
const int ATLAS_HARD_MAX_OPEN_ORDERS = 50;
const int ATLAS_HARD_MAX_TRADES_PER_CANDLE = 20;

void ApplyAtlasRuntimeMaintenance();


// Atlas decision telemetry. These values do not change Nyao's strategy logic;
// they explain the most recent entry evaluation and order attempt to Atlas.
double atlasBuyAdjustedScore = 0.0;
double atlasSellAdjustedScore = 0.0;
double atlasBuyEffectiveThreshold = 0.0;
double atlasSellEffectiveThreshold = 0.0;
bool atlasBuyEntryEligible = false;
bool atlasSellEntryEligible = false;
string atlasBuyBlockReason = "NOT_EVALUATED";
string atlasSellBlockReason = "NOT_EVALUATED";

string atlasLastGlobalBlockReason = "NONE";
bool atlasLastOrderAttempted = false;
bool atlasLastOrderSuccess = false;
string atlasLastOrderDirection = "NONE";
string atlasLastOrderMode = "NONE";
long atlasLastOrderRetcode = 0;
ulong atlasLastOrderTicket = 0;
datetime atlasLastOrderTime = 0;

void AtlasSetDecisionReason(ENUM_POSITION_TYPE dir, string reason, bool eligible=false)
{
    if(dir == POSITION_TYPE_BUY)
    {
        atlasBuyBlockReason = reason;
        atlasBuyEntryEligible = eligible;
    }
    else
    {
        atlasSellBlockReason = reason;
        atlasSellEntryEligible = eligible;
    }
}

void AtlasBeginOrderAttempt(ENUM_ORDER_TYPE orderType, string mode)
{
    atlasLastOrderAttempted = true;
    atlasLastOrderSuccess = false;
    atlasLastOrderDirection = (orderType == ORDER_TYPE_BUY) ? "BUY" : "SELL";
    atlasLastOrderMode = mode;
    atlasLastOrderRetcode = 0;
    atlasLastOrderTicket = 0;
    atlasLastOrderTime = TimeCurrent();
}

string ReadAtlasFile(string fileName)
{
    int handle = FileOpen(fileName, FILE_READ | FILE_TXT | FILE_ANSI);

    if(handle == INVALID_HANDLE)
    {
        Print("Atlas: could not open ", fileName, " error=", GetLastError());
        return "";
    }

    string content = "";

    while(!FileIsEnding(handle))
    {
        content += FileReadString(handle);
    }

    FileClose(handle);
    return content;
}


bool JsonReadBool(string json, string key, bool fallback)
{
    string pattern = "\"" + key + "\"";
    int keyPos = StringFind(json, pattern);

    if(keyPos < 0)
        return fallback;

    int colonPos = StringFind(json, ":", keyPos);

    if(colonPos < 0)
        return fallback;

    string tail = StringSubstr(json, colonPos + 1);
    StringTrimLeft(tail);

    if(StringFind(tail, "true") == 0)
        return true;

    if(StringFind(tail, "false") == 0)
        return false;

    return fallback;
}

int JsonReadInt(string json, string key, int fallback)
{
    string pattern = "\"" + key + "\"";
    int keyPos = StringFind(json, pattern);

    if(keyPos < 0)
        return fallback;

    int colonPos = StringFind(json, ":", keyPos);

    if(colonPos < 0)
        return fallback;

    string tail = StringSubstr(json, colonPos + 1);
    StringTrimLeft(tail);

    int commaPos = StringFind(tail, ",");
    int bracePos = StringFind(tail, "}");

    int endPos = -1;

    if(commaPos >= 0 && bracePos >= 0)
        endPos = MathMin(commaPos, bracePos);
    else if(commaPos >= 0)
        endPos = commaPos;
    else
        endPos = bracePos;

    if(endPos >= 0)
        tail = StringSubstr(tail, 0, endPos);

    StringTrimLeft(tail);
    StringTrimRight(tail);

    return (int)StringToInteger(tail);
}

double JsonReadDouble(string json, string key, double fallback)
{
    string pattern = "\"" + key + "\"";
    int keyPos = StringFind(json, pattern);

    if(keyPos < 0)
        return fallback;

    int colonPos = StringFind(json, ":", keyPos);

    if(colonPos < 0)
        return fallback;

    string tail = StringSubstr(json, colonPos + 1);
    StringTrimLeft(tail);

    int commaPos = StringFind(tail, ",");
    int bracePos = StringFind(tail, "}");

    int endPos = -1;

    if(commaPos >= 0 && bracePos >= 0)
        endPos = MathMin(commaPos, bracePos);
    else if(commaPos >= 0)
        endPos = commaPos;
    else
        endPos = bracePos;

    if(endPos >= 0)
        tail = StringSubstr(tail, 0, endPos);

    StringTrimLeft(tail);
    StringTrimRight(tail);

    return StringToDouble(tail);
}


string JsonReadString(string json, string key, string fallback)
{
    string pattern = "\"" + key + "\"";
    int keyPos = StringFind(json, pattern);
    if(keyPos < 0) return fallback;

    int colonPos = StringFind(json, ":", keyPos);
    if(colonPos < 0) return fallback;

    int firstQuote = StringFind(json, "\"", colonPos + 1);
    if(firstQuote < 0) return fallback;

    int secondQuote = StringFind(json, "\"", firstQuote + 1);
    if(secondQuote < 0) return fallback;

    return StringSubstr(json, firstQuote + 1, secondQuote - firstQuote - 1);
}

double AtlasClampDouble(double value, double minimum, double maximum)
{
    return MathMax(minimum, MathMin(maximum, value));
}

int AtlasClampInt(int value, int minimum, int maximum)
{
    return (int)MathMax(minimum, MathMin(maximum, value));
}

bool AtlasValidHHMM(string value)
{
    string parts[];
    if(StringSplit(value, ':', parts) != 2) return false;

    int hour = (int)StringToInteger(parts[0]);
    int minute = (int)StringToInteger(parts[1]);

    return (hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59);
}


void ReadAtlasCommand()
{
    string json = ReadAtlasFile(atlasCommandFile);
    if(json == "") return;

    int commandVersion = JsonReadInt(json, "command_version", atlasLastCommandVersion);
    if(commandVersion == atlasLastCommandVersion) return;

    int oldEMAFastPeriod = atlasRuntime.emaFastPeriod;
    int oldEMASlowPeriod = atlasRuntime.emaSlowPeriod;
    int oldRSIPeriod = atlasRuntime.rsiPeriod;
    int oldATRPeriod = atlasRuntime.atrPeriod;

    atlasEnabled = JsonReadBool(json, "enabled", atlasEnabled);
    atlasRuntime.directionalBodyLookback = AtlasClampInt(JsonReadInt(json, "directional_body_lookback", atlasRuntime.directionalBodyLookback), 1, 500);
    atlasRuntime.emaFastPeriod = AtlasClampInt(JsonReadInt(json, "ema_fast_period", atlasRuntime.emaFastPeriod), 1, 500);
    atlasRuntime.emaSlowPeriod = AtlasClampInt(JsonReadInt(json, "ema_slow_period", atlasRuntime.emaSlowPeriod), 1, 500);
    atlasRuntime.slopeLookback = AtlasClampInt(JsonReadInt(json, "slope_lookback", atlasRuntime.slopeLookback), 1, 100);
    atlasRuntime.rsiPeriod = AtlasClampInt(JsonReadInt(json, "rsi_period", atlasRuntime.rsiPeriod), 2, 500);
    atlasRuntime.atrPeriod = AtlasClampInt(JsonReadInt(json, "atr_period", atlasRuntime.atrPeriod), 1, 500);
    atlasRuntime.atrAvgLookback = AtlasClampInt(JsonReadInt(json, "atr_avg_lookback", atlasRuntime.atrAvgLookback), 1, 500);
    atlasRuntime.minVolRatioToTrade = AtlasClampDouble(JsonReadDouble(json, "min_vol_ratio_to_trade", atlasRuntime.minVolRatioToTrade), 0, 10);
    atlasRuntime.impulseLookback = AtlasClampInt(JsonReadInt(json, "impulse_lookback", atlasRuntime.impulseLookback), 1, 100);
    atlasRuntime.impulseBoostWeight = AtlasClampDouble(JsonReadDouble(json, "impulse_boost_weight", atlasRuntime.impulseBoostWeight), 0, 10);
    atlasRuntime.signalSmoothingCandles = AtlasClampInt(JsonReadInt(json, "signal_smoothing_candles", atlasRuntime.signalSmoothingCandles), 1, 10);
    atlasRuntime.currentCandleBlend = AtlasClampDouble(JsonReadDouble(json, "current_candle_blend", atlasRuntime.currentCandleBlend), 0, 1);
    atlasRuntime.velocityWindow = AtlasClampDouble(JsonReadDouble(json, "velocity_window", atlasRuntime.velocityWindow), 0.0001, 100);
    atlasRuntime.rsiOverbought = AtlasClampInt(JsonReadInt(json, "rsi_overbought", atlasRuntime.rsiOverbought), 0, 100);
    atlasRuntime.rsiOversold = AtlasClampInt(JsonReadInt(json, "rsi_oversold", atlasRuntime.rsiOversold), 0, 100);
    atlasRuntime.rsiMomentumBuy = AtlasClampInt(JsonReadInt(json, "rsi_momentum_buy", atlasRuntime.rsiMomentumBuy), 0, 100);
    atlasRuntime.rsiMomentumSell = AtlasClampInt(JsonReadInt(json, "rsi_momentum_sell", atlasRuntime.rsiMomentumSell), 0, 100);
    atlasRuntime.trendWeight = AtlasClampDouble(JsonReadDouble(json, "trend_weight", atlasRuntime.trendWeight), 0, 10);
    atlasRuntime.slopeWeight = AtlasClampDouble(JsonReadDouble(json, "slope_weight", atlasRuntime.slopeWeight), 0, 10);
    atlasRuntime.momentumBaseWeight = AtlasClampDouble(JsonReadDouble(json, "momentum_base_weight", atlasRuntime.momentumBaseWeight), 0, 10);
    atlasRuntime.momentumTriggerWeight = AtlasClampDouble(JsonReadDouble(json, "momentum_trigger_weight", atlasRuntime.momentumTriggerWeight), 0, 10);
    atlasRuntime.bodyMomentumWeight = AtlasClampDouble(JsonReadDouble(json, "body_momentum_weight", atlasRuntime.bodyMomentumWeight), 0, 10);
    atlasRuntime.chopScoreHigh = AtlasClampDouble(JsonReadDouble(json, "chop_score_high", atlasRuntime.chopScoreHigh), 0, 10);
    atlasRuntime.chopScoreMed = AtlasClampDouble(JsonReadDouble(json, "chop_score_med", atlasRuntime.chopScoreMed), 0, 10);
    atlasRuntime.chopScoreLow = AtlasClampDouble(JsonReadDouble(json, "chop_score_low", atlasRuntime.chopScoreLow), 0, 10);
    atlasRuntime.volatilityScoreHigh = AtlasClampDouble(JsonReadDouble(json, "volatility_score_high", atlasRuntime.volatilityScoreHigh), 0, 10);
    atlasRuntime.volatilityScoreLow = AtlasClampDouble(JsonReadDouble(json, "volatility_score_low", atlasRuntime.volatilityScoreLow), 0, 10);
    atlasRuntime.peakScoreWeight = AtlasClampDouble(JsonReadDouble(json, "peak_score_weight", atlasRuntime.peakScoreWeight), 0, 10);
    atlasRuntime.wickRejectionWeight = AtlasClampDouble(JsonReadDouble(json, "wick_rejection_weight", atlasRuntime.wickRejectionWeight), 0, 10);
    atlasRuntime.minBodyRatio = AtlasClampDouble(JsonReadDouble(json, "min_body_ratio", atlasRuntime.minBodyRatio), 0.0, 1000000000.0);
    atlasRuntime.enableBuyOrders = JsonReadBool(json, "enable_buy_orders", atlasRuntime.enableBuyOrders);
    atlasBuyEnabled = atlasRuntime.enableBuyOrders;
    atlasRuntime.enableSellOrders = JsonReadBool(json, "enable_sell_orders", atlasRuntime.enableSellOrders);
    atlasSellEnabled = atlasRuntime.enableSellOrders;
    atlasRuntime.enableNewBarEntryOnly = JsonReadBool(json, "enable_new_bar_entry_only", atlasRuntime.enableNewBarEntryOnly);
    atlasRuntime.enableMaxSpreadFilter = JsonReadBool(json, "enable_max_spread_filter", atlasRuntime.enableMaxSpreadFilter);
    atlasRuntime.maxSpreadPoints = AtlasClampDouble(JsonReadDouble(json, "max_spread_points", atlasRuntime.maxSpreadPoints), 0.0, 1000000000.0);
    atlasRuntime.maxSpreadAtrRatio = AtlasClampDouble(JsonReadDouble(json, "max_spread_atr_ratio", atlasRuntime.maxSpreadAtrRatio), 0, 10);
    atlasRuntime.baseLotSize = AtlasClampDouble(JsonReadDouble(json, "base_lot_size", atlasRuntime.baseLotSize), 0, 5);
    atlasRuntime.maxOpenOrders = AtlasClampInt(JsonReadInt(json, "max_open_orders", atlasRuntime.maxOpenOrders), 1, 50);
    atlasRuntime.maxTradesPerCandle = AtlasClampInt(JsonReadInt(json, "max_trades_per_candle", atlasRuntime.maxTradesPerCandle), 0, 20);
    atlasRuntime.consecutiveCandleThresholdBoost = AtlasClampDouble(JsonReadDouble(json, "consecutive_candle_threshold_boost", atlasRuntime.consecutiveCandleThresholdBoost), 0, 10);
    atlasRuntime.maxConsecutiveCandleBoosts = AtlasClampInt(JsonReadInt(json, "max_consecutive_candle_boosts", atlasRuntime.maxConsecutiveCandleBoosts), 0, 100);
    atlasRuntime.zonePoints = AtlasClampDouble(JsonReadDouble(json, "zone_points", atlasRuntime.zonePoints), 0.0, 1000000000.0);
    atlasRuntime.buyDuplicateMultiplier = AtlasClampDouble(JsonReadDouble(json, "buy_duplicate_multiplier", atlasRuntime.buyDuplicateMultiplier), 0, 100);
    atlasRuntime.sellDuplicateMultiplier = AtlasClampDouble(JsonReadDouble(json, "sell_duplicate_multiplier", atlasRuntime.sellDuplicateMultiplier), 0, 100);
    atlasRuntime.minBreakEvenProfit = AtlasClampDouble(JsonReadDouble(json, "min_break_even_profit", atlasRuntime.minBreakEvenProfit), 0.0, 1000000000.0);
    atlasRuntime.profitThresholdMultiplier = AtlasClampDouble(JsonReadDouble(json, "profit_threshold_multiplier", atlasRuntime.profitThresholdMultiplier), 0, 100);
    atlasRuntime.lossThresholdMultiplier = AtlasClampDouble(JsonReadDouble(json, "loss_threshold_multiplier", atlasRuntime.lossThresholdMultiplier), 0, 100);
    atlasRuntime.minBuySignalScore = AtlasClampDouble(JsonReadDouble(json, "min_buy_signal_score", atlasRuntime.minBuySignalScore), 0, 10);
    atlasRuntime.minSellSignalScore = AtlasClampDouble(JsonReadDouble(json, "min_sell_signal_score", atlasRuntime.minSellSignalScore), 0, 10);
    atlasRuntime.enableLimitEntry = JsonReadBool(json, "enable_limit_entry", atlasRuntime.enableLimitEntry);
    atlasRuntime.limitEntryAnchor = (ENUM_LIMIT_ANCHOR)AtlasClampInt(JsonReadInt(json, "limit_entry_anchor", (int)atlasRuntime.limitEntryAnchor), 0, 3);
    atlasRuntime.limitEntryAtrFraction = AtlasClampDouble(JsonReadDouble(json, "limit_entry_atr_fraction", atlasRuntime.limitEntryAtrFraction), 0, 10);
    atlasRuntime.limitEntryExpiryBars = AtlasClampInt(JsonReadInt(json, "limit_entry_expiry_bars", atlasRuntime.limitEntryExpiryBars), 0, 1000);
    atlasRuntime.limitEntryCancelOnFlip = JsonReadBool(json, "limit_entry_cancel_on_flip", atlasRuntime.limitEntryCancelOnFlip);
    atlasRuntime.enableSignalDampening = JsonReadBool(json, "enable_signal_dampening", atlasRuntime.enableSignalDampening);
    atlasRuntime.maxLosingPositionsSameDir = AtlasClampInt(JsonReadInt(json, "max_losing_positions_same_dir", atlasRuntime.maxLosingPositionsSameDir), 0, 50);
    atlasRuntime.losingPosScorePenalty = AtlasClampDouble(JsonReadDouble(json, "losing_pos_score_penalty", atlasRuntime.losingPosScorePenalty), 0, 10);
    atlasRuntime.drawdownThresholdPct = AtlasClampDouble(JsonReadDouble(json, "drawdown_threshold_pct", atlasRuntime.drawdownThresholdPct), 0, 100);
    atlasRuntime.drawdownScoreBoost = AtlasClampDouble(JsonReadDouble(json, "drawdown_score_boost", atlasRuntime.drawdownScoreBoost), 0, 10);
    atlasRuntime.consecutiveLossesBeforeCooldown = AtlasClampInt(JsonReadInt(json, "consecutive_losses_before_cooldown", atlasRuntime.consecutiveLossesBeforeCooldown), 0, 100);
    atlasRuntime.consecutiveLossCooldownBars = AtlasClampInt(JsonReadInt(json, "consecutive_loss_cooldown_bars", atlasRuntime.consecutiveLossCooldownBars), 0, 1000);
    atlasRuntime.enableLossManagement = JsonReadBool(json, "enable_loss_management", atlasRuntime.enableLossManagement);
    atlasRuntime.maxHoldingLossPositions = AtlasClampInt(JsonReadInt(json, "max_holding_loss_positions", atlasRuntime.maxHoldingLossPositions), 0, 50);
    atlasRuntime.minHealthScore = AtlasClampDouble(JsonReadDouble(json, "min_health_score", atlasRuntime.minHealthScore), 0, 1);
    atlasRuntime.maxAdverseAtr = AtlasClampDouble(JsonReadDouble(json, "max_adverse_atr", atlasRuntime.maxAdverseAtr), 0, 100);
    atlasRuntime.healthTrendWeight = AtlasClampDouble(JsonReadDouble(json, "health_trend_weight", atlasRuntime.healthTrendWeight), 0.0, 1000000000.0);
    atlasRuntime.healthRsiWeight = AtlasClampDouble(JsonReadDouble(json, "health_rsi_weight", atlasRuntime.healthRsiWeight), 0.0, 1000000000.0);
    atlasRuntime.healthAtrWeight = AtlasClampDouble(JsonReadDouble(json, "health_atr_weight", atlasRuntime.healthAtrWeight), 0.0, 1000000000.0);
    atlasRuntime.healthSwingWeight = AtlasClampDouble(JsonReadDouble(json, "health_swing_weight", atlasRuntime.healthSwingWeight), 0.0, 1000000000.0);
    atlasRuntime.healthRsiBuyMin = AtlasClampDouble(JsonReadDouble(json, "health_rsi_buy_min", atlasRuntime.healthRsiBuyMin), 0, 100);
    atlasRuntime.healthRsiSellMax = AtlasClampDouble(JsonReadDouble(json, "health_rsi_sell_max", atlasRuntime.healthRsiSellMax), 0, 100);
    atlasRuntime.healthSwingLookback = AtlasClampInt(JsonReadInt(json, "health_swing_lookback", atlasRuntime.healthSwingLookback), 1, 1000);
    atlasRuntime.healthGraceBars = AtlasClampInt(JsonReadInt(json, "health_grace_bars", atlasRuntime.healthGraceBars), 0, 1000);
    atlasRuntime.enablePartialClose = JsonReadBool(json, "enable_partial_close", atlasRuntime.enablePartialClose);
    atlasRuntime.partialClose75Pct = AtlasClampDouble(JsonReadDouble(json, "partial_close75_pct", atlasRuntime.partialClose75Pct), 0, 1);
    atlasRuntime.partialClose50Pct = AtlasClampDouble(JsonReadDouble(json, "partial_close50_pct", atlasRuntime.partialClose50Pct), 0, 1);
    atlasRuntime.partialClose25Pct = AtlasClampDouble(JsonReadDouble(json, "partial_close25_pct", atlasRuntime.partialClose25Pct), 0, 1);
    atlasRuntime.enableHealthSlTightening = JsonReadBool(json, "enable_health_sl_tightening", atlasRuntime.enableHealthSlTightening);
    atlasRuntime.slTightenAtrMultiplier = AtlasClampDouble(JsonReadDouble(json, "sl_tighten_atr_multiplier", atlasRuntime.slTightenAtrMultiplier), 0.0, 1000000000.0);
    atlasRuntime.slTightenMinHealthPct = AtlasClampDouble(JsonReadDouble(json, "sl_tighten_min_health_pct", atlasRuntime.slTightenMinHealthPct), 0, 1);
    atlasRuntime.enableBreakEvenOnSpread = JsonReadBool(json, "enable_break_even_on_spread", atlasRuntime.enableBreakEvenOnSpread);
    atlasRuntime.breakEvenSpreadMultiplier = AtlasClampDouble(JsonReadDouble(json, "break_even_spread_multiplier", atlasRuntime.breakEvenSpreadMultiplier), 0.0, 1000000000.0);
    atlasRuntime.enableVirtualSlReentry = JsonReadBool(json, "enable_virtual_sl_reentry", atlasRuntime.enableVirtualSlReentry);
    atlasRuntime.reentryRespectsNewBarGate = JsonReadBool(json, "reentry_respects_new_bar_gate", atlasRuntime.reentryRespectsNewBarGate);
    atlasRuntime.reentryMinSignalPct = AtlasClampDouble(JsonReadDouble(json, "reentry_min_signal_pct", atlasRuntime.reentryMinSignalPct), 0, 2);
    atlasRuntime.enableProfitOffsetSl = JsonReadBool(json, "enable_profit_offset_sl", atlasRuntime.enableProfitOffsetSl);
    atlasRuntime.consecutiveWinsRequired = AtlasClampInt(JsonReadInt(json, "consecutive_wins_required", atlasRuntime.consecutiveWinsRequired), 0, 100);
    atlasRuntime.minOffsetProfit = AtlasClampDouble(JsonReadDouble(json, "min_offset_profit", atlasRuntime.minOffsetProfit), 0.0, 1000000000.0);
    atlasRuntime.enableHedgeChain = JsonReadBool(json, "enable_hedge_chain", atlasRuntime.enableHedgeChain);
    atlasRuntime.hedgeTriggerAtr = AtlasClampDouble(JsonReadDouble(json, "hedge_trigger_atr", atlasRuntime.hedgeTriggerAtr), 0, 100);
    atlasRuntime.hedgeRequireSignal = JsonReadBool(json, "hedge_require_signal", atlasRuntime.hedgeRequireSignal);
    atlasRuntime.hedgeMinSignalScore = AtlasClampDouble(JsonReadDouble(json, "hedge_min_signal_score", atlasRuntime.hedgeMinSignalScore), 0, 10);
    atlasRuntime.hedgeAutoLot = JsonReadBool(json, "hedge_auto_lot", atlasRuntime.hedgeAutoLot);
    atlasRuntime.hedgeRecoveryAtr = AtlasClampDouble(JsonReadDouble(json, "hedge_recovery_atr", atlasRuntime.hedgeRecoveryAtr), 0, 100);
    atlasRuntime.hedgeLotMultiplier = AtlasClampDouble(JsonReadDouble(json, "hedge_lot_multiplier", atlasRuntime.hedgeLotMultiplier), 0, 20);
    atlasRuntime.hedgeMaxLot = AtlasClampDouble(JsonReadDouble(json, "hedge_max_lot", atlasRuntime.hedgeMaxLot), 0, 5);
    atlasRuntime.hedgeRecoveryPct = AtlasClampDouble(JsonReadDouble(json, "hedge_recovery_pct", atlasRuntime.hedgeRecoveryPct), 0, 1000);
    atlasRuntime.hedgeRollMinProfit = AtlasClampDouble(JsonReadDouble(json, "hedge_roll_min_profit", atlasRuntime.hedgeRollMinProfit), 0.0, 1000000000.0);
    atlasRuntime.hedgeCycleLevels = AtlasClampInt(JsonReadInt(json, "hedge_cycle_levels", atlasRuntime.hedgeCycleLevels), 1, 20);
    atlasRuntime.enableHedgeCycleReset = JsonReadBool(json, "enable_hedge_cycle_reset", atlasRuntime.enableHedgeCycleReset);
    atlasRuntime.hedgeCyclePartialPct = AtlasClampDouble(JsonReadDouble(json, "hedge_cycle_partial_pct", atlasRuntime.hedgeCyclePartialPct), 0, 100);
    atlasRuntime.hedgeMaxCycles = AtlasClampInt(JsonReadInt(json, "hedge_max_cycles", atlasRuntime.hedgeMaxCycles), 0, 100);
    atlasRuntime.hedgeMaxChainLossUsd = AtlasClampDouble(JsonReadDouble(json, "hedge_max_chain_loss_usd", atlasRuntime.hedgeMaxChainLossUsd), 0.0, 1000000000.0);
    atlasRuntime.hedgeMaxChainLossPct = AtlasClampDouble(JsonReadDouble(json, "hedge_max_chain_loss_pct", atlasRuntime.hedgeMaxChainLossPct), 0, 100);
    atlasRuntime.hedgeClearRootSl = JsonReadBool(json, "hedge_clear_root_sl", atlasRuntime.hedgeClearRootSl);
    atlasRuntime.hedgeTrailAtr = AtlasClampDouble(JsonReadDouble(json, "hedge_trail_atr", atlasRuntime.hedgeTrailAtr), 0, 100);
    atlasRuntime.enableDynamicLots = JsonReadBool(json, "enable_dynamic_lots", atlasRuntime.enableDynamicLots);
    atlasRuntime.equityDropPercent = AtlasClampDouble(JsonReadDouble(json, "equity_drop_percent", atlasRuntime.equityDropPercent), 0, 100);
    atlasRuntime.maxEquityDropLotSteps = AtlasClampInt(JsonReadInt(json, "max_equity_drop_lot_steps", atlasRuntime.maxEquityDropLotSteps), 0, 100);
    atlasRuntime.minSignalStrengthForLot = AtlasClampDouble(JsonReadDouble(json, "min_signal_strength_for_lot", atlasRuntime.minSignalStrengthForLot), 0, 10);
    atlasRuntime.lotStepSize = AtlasClampDouble(JsonReadDouble(json, "lot_step_size", atlasRuntime.lotStepSize), 0, 5);
    atlasRuntime.maxLotSize = AtlasClampDouble(JsonReadDouble(json, "max_lot_size", atlasRuntime.maxLotSize), 0, 5);
    atlasRuntime.enableBasketStop = JsonReadBool(json, "enable_basket_stop", atlasRuntime.enableBasketStop);
    atlasRuntime.maxBasketLossPct = AtlasClampDouble(JsonReadDouble(json, "max_basket_loss_pct", atlasRuntime.maxBasketLossPct), 0, 100);
    atlasRuntime.minEquityPercent = AtlasClampDouble(JsonReadDouble(json, "min_equity_percent", atlasRuntime.minEquityPercent), 0.0, 1000000000.0);
    atlasRuntime.maxDrawdownFromPeak = AtlasClampDouble(JsonReadDouble(json, "max_drawdown_from_peak", atlasRuntime.maxDrawdownFromPeak), 0.0, 1000000000.0);
    atlasRuntime.pauseMinutes = AtlasClampInt(JsonReadInt(json, "pause_minutes", atlasRuntime.pauseMinutes), 0, 1440);
    atlasRuntime.pauseMinutesMultiplier = AtlasClampDouble(JsonReadDouble(json, "pause_minutes_multiplier", atlasRuntime.pauseMinutesMultiplier), 0, 100);
    atlasRuntime.maxPauseMinutes = AtlasClampInt(JsonReadInt(json, "max_pause_minutes", atlasRuntime.maxPauseMinutes), 0, 10080);
    atlasRuntime.maxMinEquityTriggers = AtlasClampInt(JsonReadInt(json, "max_min_equity_triggers", atlasRuntime.maxMinEquityTriggers), 0, 1000);
    atlasRuntime.resetOnNewPeak = JsonReadBool(json, "reset_on_new_peak", atlasRuntime.resetOnNewPeak);
    atlasRuntime.targetEquity = AtlasClampDouble(JsonReadDouble(json, "target_equity", atlasRuntime.targetEquity), 0.0, 1000000000.0);
    atlasRuntime.minimumEquity = AtlasClampDouble(JsonReadDouble(json, "minimum_equity", atlasRuntime.minimumEquity), 0.0, 1000000000.0);
    atlasRuntime.enableTakeProfit = JsonReadBool(json, "enable_take_profit", atlasRuntime.enableTakeProfit);
    atlasRuntime.tpInputType = (ENUM_INPUT_TYPE)AtlasClampInt(JsonReadInt(json, "tp_input_type", (int)atlasRuntime.tpInputType), 0, 2);
    atlasRuntime.tpValue = AtlasClampDouble(JsonReadDouble(json, "tp_value", atlasRuntime.tpValue), 0.0, 1000000000.0);
    atlasRuntime.enableStopLoss = JsonReadBool(json, "enable_stop_loss", atlasRuntime.enableStopLoss);
    atlasRuntime.slInputType = (ENUM_INPUT_TYPE)AtlasClampInt(JsonReadInt(json, "sl_input_type", (int)atlasRuntime.slInputType), 0, 2);
    atlasRuntime.slValue = AtlasClampDouble(JsonReadDouble(json, "sl_value", atlasRuntime.slValue), 0.0, 1000000000.0);
    atlasRuntime.enableRiskReward = JsonReadBool(json, "enable_risk_reward", atlasRuntime.enableRiskReward);
    atlasRuntime.rrRiskMode = (ENUM_RR_RISK_MODE)AtlasClampInt(JsonReadInt(json, "rr_risk_mode", (int)atlasRuntime.rrRiskMode), 0, 1);
    atlasRuntime.rrRiskInputType = (ENUM_INPUT_TYPE)AtlasClampInt(JsonReadInt(json, "rr_risk_input_type", (int)atlasRuntime.rrRiskInputType), 0, 2);
    atlasRuntime.rrRiskValue = AtlasClampDouble(JsonReadDouble(json, "rr_risk_value", atlasRuntime.rrRiskValue), 0.0, 1000000000.0);
    atlasRuntime.rrAtrMultiplier = AtlasClampDouble(JsonReadDouble(json, "rr_atr_multiplier", atlasRuntime.rrAtrMultiplier), 0, 100);
    atlasRuntime.riskRewardRatio = AtlasClampDouble(JsonReadDouble(json, "risk_reward_ratio", atlasRuntime.riskRewardRatio), 0, 100);
    atlasRuntime.enableTrailing = JsonReadBool(json, "enable_trailing", atlasRuntime.enableTrailing);
    atlasRuntime.trailingEnableBreakEvenLock = JsonReadBool(json, "trailing_enable_break_even_lock", atlasRuntime.trailingEnableBreakEvenLock);
    atlasRuntime.trailingSlOnProfitableOnly = JsonReadBool(json, "trailing_sl_on_profitable_only", atlasRuntime.trailingSlOnProfitableOnly);
    atlasRuntime.enableAdaptiveTp = JsonReadBool(json, "enable_adaptive_tp", atlasRuntime.enableAdaptiveTp);
    atlasRuntime.enableAdaptiveSl = JsonReadBool(json, "enable_adaptive_sl", atlasRuntime.enableAdaptiveSl);
    atlasRuntime.tsInputType = (ENUM_INPUT_TYPE)AtlasClampInt(JsonReadInt(json, "ts_input_type", (int)atlasRuntime.tsInputType), 0, 2);
    atlasRuntime.trailingDistanceValue = AtlasClampDouble(JsonReadDouble(json, "trailing_distance_value", atlasRuntime.trailingDistanceValue), 0.0, 1000000000.0);
    atlasRuntime.trailingValueMultiplier = AtlasClampDouble(JsonReadDouble(json, "trailing_value_multiplier", atlasRuntime.trailingValueMultiplier), 0, 100);
    atlasRuntime.enableDiscordAlerts = JsonReadBool(json, "enable_discord_alerts", atlasRuntime.enableDiscordAlerts);
    atlasRuntime.enableTradingHours = JsonReadBool(json, "enable_trading_hours", atlasRuntime.enableTradingHours);
    {
        string requested = JsonReadString(json, "trading_start_time", atlasRuntime.tradingStartTime);
        if(AtlasValidHHMM(requested)) atlasRuntime.tradingStartTime = requested;
    }
    {
        string requested = JsonReadString(json, "trading_end_time", atlasRuntime.tradingEndTime);
        if(AtlasValidHHMM(requested)) atlasRuntime.tradingEndTime = requested;
    }
    atlasRuntime.enableReports = JsonReadBool(json, "enable_reports", atlasRuntime.enableReports);
    atlasRuntime.sendReportEveryHour = AtlasClampInt(JsonReadInt(json, "send_report_every_hour", atlasRuntime.sendReportEveryHour), 1, 168);
    atlasRuntime.enableMarketCloseFilter = JsonReadBool(json, "enable_market_close_filter", atlasRuntime.enableMarketCloseFilter);
    atlasRuntime.minutesBeforeClose = AtlasClampInt(JsonReadInt(json, "minutes_before_close", atlasRuntime.minutesBeforeClose), 0, 1440);
    atlasRuntime.enableNewsFilter = JsonReadBool(json, "enable_news_filter", atlasRuntime.enableNewsFilter);
    atlasRuntime.newsMinutesBefore = AtlasClampInt(JsonReadInt(json, "news_minutes_before", atlasRuntime.newsMinutesBefore), 0, 1440);
    atlasRuntime.newsMinutesAfter = AtlasClampInt(JsonReadInt(json, "news_minutes_after", atlasRuntime.newsMinutesAfter), 0, 1440);
    atlasRuntime.enableLeveragePause = JsonReadBool(json, "enable_leverage_pause", atlasRuntime.enableLeveragePause);
    atlasRuntime.enableLogging = JsonReadBool(json, "enable_logging", atlasRuntime.enableLogging);

    double brokerMinLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double brokerMaxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    if(brokerMinLot <= 0) brokerMinLot = 0.01;
    if(brokerMaxLot <= 0) brokerMaxLot = ATLAS_HARD_MAX_LOT;
    double localMaxLot = MathMin(brokerMaxLot, ATLAS_HARD_MAX_LOT);
    atlasRuntime.maxLotSize = AtlasClampDouble(atlasRuntime.maxLotSize, brokerMinLot, localMaxLot);
    atlasRuntime.baseLotSize = AtlasClampDouble(atlasRuntime.baseLotSize, brokerMinLot, atlasRuntime.maxLotSize);
    atlasRuntime.hedgeMaxLot = AtlasClampDouble(atlasRuntime.hedgeMaxLot, brokerMinLot, localMaxLot);
    atlasRuntime.lotStepSize = AtlasClampDouble(atlasRuntime.lotStepSize, 0.0, localMaxLot);
    atlasRuntime.maxOpenOrders = AtlasClampInt(atlasRuntime.maxOpenOrders, 1, ATLAS_HARD_MAX_OPEN_ORDERS);
    atlasRuntime.maxTradesPerCandle = AtlasClampInt(atlasRuntime.maxTradesPerCandle, 0, ATLAS_HARD_MAX_TRADES_PER_CANDLE);

    atlasBuyEffectiveThreshold = atlasRuntime.minBuySignalScore;
    atlasSellEffectiveThreshold = atlasRuntime.minSellSignalScore;

    if(oldEMAFastPeriod != atlasRuntime.emaFastPeriod ||
       oldEMASlowPeriod != atlasRuntime.emaSlowPeriod ||
       oldRSIPeriod != atlasRuntime.rsiPeriod ||
       oldATRPeriod != atlasRuntime.atrPeriod)
        atlasStructuralConfigDirty = true;

    atlasHealthWeightsDirty = true;
    atlasLastCommandVersion = commandVersion;

    Print(
        "Atlas command applied. Version=", atlasLastCommandVersion,
        " Enabled=", atlasEnabled,
        " Buy=", atlasRuntime.enableBuyOrders,
        " Sell=", atlasRuntime.enableSellOrders,
        " BuyThreshold=", DoubleToString(atlasRuntime.minBuySignalScore, 2),
        " SellThreshold=", DoubleToString(atlasRuntime.minSellSignalScore, 2),
        " BaseLot=", DoubleToString(atlasRuntime.baseLotSize, 2),
        " MaxOrders=", atlasRuntime.maxOpenOrders,
        " TradesPerCandle=", atlasRuntime.maxTradesPerCandle,
        " NewBarOnly=", atlasRuntime.enableNewBarEntryOnly,
        " Hedge=", atlasRuntime.enableHedgeChain,
        " DynamicLots=", atlasRuntime.enableDynamicLots
    );
}





// Normalized Health Weights
double normHealthTrendWeight = 0;
double normHealthRSIWeight = 0;
double normHealthATRWeight = 0;
double normHealthSwingWeight = 0;

// Duplicate Signal Filter Variables
datetime startTime = 0;                                   // EA Start Time
datetime lastDailyReportTime = 0;                         // Last time daily report was sent
double lastReportEquity = 0;                              // Equity at last report

// Pause Tracking
int totalPauseCount = 0;                                  // Total number of times trading was paused
double totalPauseDurationMinutes = 0;                     // Total duration of pauses in minutes


int emaFastHandle = INVALID_HANDLE;                       // Handle for Fast EMA
int emaSlowHandle = INVALID_HANDLE;                       // Handle for Slow EMA
int rsiHandle = INVALID_HANDLE;                           // Handle for RSI
int atrSignalHandle = INVALID_HANDLE;                     // Handle for Signal ATR

// Signal Strength Structure - Indicator-Based Scoring System
// Weights are adjustable via Score Weight Settings inputs
struct SignalStrength
{
    double avgBody;                                       // Average body size of matching candles
    double bodySignal;                                    // Body size of signal candle
    double ratio;                                         // Ratio of bodySignal / avgBody
    double upperWick;                                     // Upper wick size
    double lowerWick;                                     // Lower wick size
    double rejection;                                     // Wick to body ratio
    double penaltyBody;                                   // Penalty from body ratio
    double penaltyWick;                                   // Penalty from wick rejection
    double finalScore;                                    // 0.00-10.00 Score
    double trendScore;                                    // Trend Component (0-3)
    double momentumScore;                                 // Momentum Component (0-3)
    double chopScore;                                     // Chop Component (0-2)
    double peakScore;                                     // Peak Component (0-1)
    double volatilityScore;                               // Volatility Component (0-1)
    double impulseStrength;                               // 0.0-1.0 Impulse Strength
    double velocity;                                      // Current Score - Previous Score
    double normalizedVelocity;                            // 0.0-1.0 Normalized Velocity
    string reasoning;                                     // Detailed explanation
};

// Position Health Structure - Measurement-Based Revalidation
// Evaluates whether a position's trade thesis is still valid
struct PositionHealth
{
    double healthScore;                                   // 0.0 (dead) to 1.0 (fully healthy)
    bool trendValid;                                      // EMA still aligned with position direction?
    bool momentumValid;                                   // RSI still in favorable zone?
    double adverseATR;                                    // How many ATRs moved against position
    bool swingValid;                                      // Price hasn't broken swing level?
    bool inGracePeriod;                                   // Position too new for health check?
    string reason;                                        // Human-readable invalidation reason
};

// Managed Position Structure - For Position Tracking 
// Stores position info to avoid repeated MQL function calls
struct ManagedPosition
{
    ulong ticket;                                         // Position ticket ID
    ENUM_POSITION_TYPE type;                              // Buy or Sell
    double signalScore;                                   // Initial signal score
    double entryPrice;                                    // Entry price for adverse excursion calc
    int partialCloseLevel;                                // 0=none, 1=75% triggered, 2=50% triggered, 3=fully closed
    bool breakEvenLocked;                                 // Whether SL has been moved to break-even by loss mgmt
    int profitOffsetConsecWins;                           // Consecutive winning trades closed since this position opened
    double profitOffsetAccumulated;                       // Accumulated profit from consecutive wins (USD)
    double profitOffsetOriginalSL;                        // Original SL price when position was opened
    ulong chainId;                                       // Rolling-hedge chain id (current cycle's root ticket); 0 = standalone
    int hedgeLevel;                                      // Level within the cycle: 0 = root, 1+ = each successive hedge
    double chainAnchorLoss;                              // Cycle start loss ($, positive) carried on every leg of the cycle
    int cycleNum;                                        // Which cycle this leg belongs to (0 = first; +1 on each reseed)
    bool noRehedge;                                      // true = exhausted chain released to loss mgmt; never start a new chain on it
    bool hedgeGraduated;                                 // true = former chain leg; trail with HedgeTrailATR (lot-independent) not the $ distance
    double hedgeLockProfit;                              // min profit ($) to keep locked on a graduated hedge (recovery floor); 0 = none
};


// Managed positions array is declared before Atlas status telemetry so
// observability can include hedge/recovery metadata for each live position.
ManagedPosition managedPositions[];
int managedPositionCount = 0;

string AtlasJsonEscape(string value)
{
    StringReplace(value, "\\", "\\\\");
    StringReplace(value, "\"", "\\\"");
    StringReplace(value, "\r", "\\r");
    StringReplace(value, "\n", "\\n");
    StringReplace(value, "\t", "\\t");
    return value;
}

void AtlasResetSignalStrength(SignalStrength &strength)
{
    strength.avgBody = 0.0;
    strength.bodySignal = 0.0;
    strength.ratio = 0.0;
    strength.upperWick = 0.0;
    strength.lowerWick = 0.0;
    strength.rejection = 0.0;
    strength.penaltyBody = 0.0;
    strength.penaltyWick = 0.0;
    strength.finalScore = 0.0;
    strength.trendScore = 0.0;
    strength.momentumScore = 0.0;
    strength.chopScore = 0.0;
    strength.peakScore = 0.0;
    strength.volatilityScore = 0.0;
    strength.impulseStrength = 0.0;
    strength.velocity = 0.0;
    strength.normalizedVelocity = 0.0;
    strength.reasoning = "";
}

void WriteAtlasStatus()
{
    SignalStrength buyStrength;
    SignalStrength sellStrength;
    AtlasResetSignalStrength(buyStrength);
    AtlasResetSignalStrength(sellStrength);

    bool signalTelemetryReady =
        passwordVerified &&
        emaFastHandle != INVALID_HANDLE &&
        emaSlowHandle != INVALID_HANDLE &&
        rsiHandle != INVALID_HANDLE &&
        atrSignalHandle != INVALID_HANDLE;

    if(signalTelemetryReady)
    {
        buyStrength = GetSignalStrength(ORDER_TYPE_BUY);
        sellStrength = GetSignalStrength(ORDER_TYPE_SELL);
    }

    double buyScore = buyStrength.finalScore;
    double sellScore = sellStrength.finalScore;

    MqlDateTime atlasUtcTime;
    TimeToStruct(TimeGMT(), atlasUtcTime);

    string atlasTimestamp = StringFormat(
        "%04d-%02d-%02dT%02d:%02d:%02dZ",
        atlasUtcTime.year,
        atlasUtcTime.mon,
        atlasUtcTime.day,
        atlasUtcTime.hour,
        atlasUtcTime.min,
        atlasUtcTime.sec
    );

    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double floatingProfit = AccountInfoDouble(ACCOUNT_PROFIT);
    double accountMargin = AccountInfoDouble(ACCOUNT_MARGIN);
    double freeMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
    double marginLevel = AccountInfoDouble(ACCOUNT_MARGIN_LEVEL);
    long accountLeverage = AccountInfoInteger(ACCOUNT_LEVERAGE);

    double equityDrawdownUsd = MathMax(0.0, peakEquity - equity);
    double equityDrawdownPct =
        (peakEquity > 0.0)
            ? (equityDrawdownUsd / peakEquity) * 100.0
            : 0.0;

    datetime atlasCurrentBarTime = iTime(_Symbol, _Period, 0);
    bool atlasNewBarReady =
        !atlasRuntime.enableNewBarEntryOnly ||
        (lastEntryBarTime != atlasCurrentBarTime);

    bool atlasCooldownActive =
        atlasRuntime.enableSignalDampening &&
        cooldownUntilBarTime > atlasCurrentBarTime;

    long pauseUntilEpoch = 0;
    if(isPaused && currentPauseDuration > 0 && pauseStartTime > 0)
        pauseUntilEpoch = (long)(pauseStartTime + currentPauseDuration * 60);

    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double spreadPoints =
        (_Point > 0.0 && ask > 0.0 && bid > 0.0)
            ? (ask - bid) / _Point
            : 0.0;

    double currentAtr = 0.0;
    double averageAtr = 0.0;
    double volatilityRatio = 0.0;
    double atrPoints = 0.0;

    if(atrSignalHandle != INVALID_HANDLE)
    {
        double atrCurrentBuffer[];
        ArraySetAsSeries(atrCurrentBuffer, true);

        if(CopyBuffer(atrSignalHandle, 0, 0, 1, atrCurrentBuffer) == 1)
        {
            currentAtr = atrCurrentBuffer[0];
            if(_Point > 0.0)
                atrPoints = currentAtr / _Point;
        }

        int atrLookback = MathMax(1, atlasRuntime.atrAvgLookback);
        double atrHistory[];
        ArraySetAsSeries(atrHistory, true);

        int copiedAtr = CopyBuffer(
            atrSignalHandle,
            0,
            1,
            atrLookback,
            atrHistory
        );

        if(copiedAtr > 0)
        {
            double atrSum = 0.0;
            for(int ai = 0; ai < copiedAtr; ai++)
                atrSum += atrHistory[ai];

            averageAtr = atrSum / copiedAtr;
        }

        if(averageAtr > 0.0)
            volatilityRatio = currentAtr / averageAtr;
    }

    double effectiveSpreadCapPoints = atlasRuntime.maxSpreadPoints;
    if(effectiveSpreadCapPoints <= 0.0 && atrPoints > 0.0)
        effectiveSpreadCapPoints =
            atrPoints * atlasRuntime.maxSpreadAtrRatio;

    bool spreadWithinLimit =
        !atlasRuntime.enableMaxSpreadFilter ||
        effectiveSpreadCapPoints <= 0.0 ||
        spreadPoints <= effectiveSpreadCapPoints;

    int strategyPositionCount = 0;
    int buyPositionCount = 0;
    int sellPositionCount = 0;
    int losingPositionCount = 0;
    int winningPositionCount = 0;

    double totalLots = 0.0;
    double buyLots = 0.0;
    double sellLots = 0.0;
    double strategyFloatingPl = 0.0;
    double strategySwap = 0.0;
    double grossFloatingProfit = 0.0;
    double grossFloatingLoss = 0.0;
    double largestWinningPosition = 0.0;
    double largestLosingPosition = 0.0;
    double grossNotionalExposure = 0.0;
    double buyNotionalExposure = 0.0;
    double sellNotionalExposure = 0.0;

    int activeHedgeChainCount = 0;
    int hedgeChainPositionCount = 0;
    int maxActiveHedgeLevel = 0;
    int maxActiveHedgeCycle = 0;
    double hedgeChainLots = 0.0;
    double hedgeChainFloatingPl = 0.0;
    ulong seenChainIds[];

    string positionsJson = "[";
    double contractSize =
        SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);

    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        if(!PositionSelectByTicket(ticket)) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

        ENUM_POSITION_TYPE posType =
            (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

        double volume = PositionGetDouble(POSITION_VOLUME);
        double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
        double currentPrice = PositionGetDouble(POSITION_PRICE_CURRENT);
        double sl = PositionGetDouble(POSITION_SL);
        double tp = PositionGetDouble(POSITION_TP);
        double profit = PositionGetDouble(POSITION_PROFIT);
        double swap = PositionGetDouble(POSITION_SWAP);
        datetime positionTime =
            (datetime)PositionGetInteger(POSITION_TIME);

        double netPl = profit + swap;
        double notional =
            (contractSize > 0.0 && currentPrice > 0.0)
                ? volume * contractSize * currentPrice
                : 0.0;

        strategyPositionCount++;
        totalLots += volume;
        strategyFloatingPl += netPl;
        strategySwap += swap;
        grossNotionalExposure += notional;

        if(posType == POSITION_TYPE_BUY)
        {
            buyPositionCount++;
            buyLots += volume;
            buyNotionalExposure += notional;
        }
        else
        {
            sellPositionCount++;
            sellLots += volume;
            sellNotionalExposure += notional;
        }

        if(netPl < 0.0)
        {
            losingPositionCount++;
            grossFloatingLoss += netPl;
            if(netPl < largestLosingPosition)
                largestLosingPosition = netPl;
        }
        else if(netPl > 0.0)
        {
            winningPositionCount++;
            grossFloatingProfit += netPl;
            if(netPl > largestWinningPosition)
                largestWinningPosition = netPl;
        }

        int managedIndex = GetManagedPositionIndex(ticket);

        double managedSignalScore = 0.0;
        int partialCloseLevel = 0;
        bool breakEvenLocked = false;
        ulong chainId = 0;
        int hedgeLevel = 0;
        int cycleNum = 0;
        bool noRehedge = false;
        bool hedgeGraduated = false;
        double hedgeLockProfit = 0.0;

        if(managedIndex >= 0 && managedIndex < managedPositionCount)
        {
            managedSignalScore = managedPositions[managedIndex].signalScore;
            partialCloseLevel = managedPositions[managedIndex].partialCloseLevel;
            breakEvenLocked = managedPositions[managedIndex].breakEvenLocked;
            chainId = managedPositions[managedIndex].chainId;
            hedgeLevel = managedPositions[managedIndex].hedgeLevel;
            cycleNum = managedPositions[managedIndex].cycleNum;
            noRehedge = managedPositions[managedIndex].noRehedge;
            hedgeGraduated = managedPositions[managedIndex].hedgeGraduated;
            hedgeLockProfit = managedPositions[managedIndex].hedgeLockProfit;
        }

        if(chainId != 0)
        {
            hedgeChainPositionCount++;
            hedgeChainLots += volume;
            hedgeChainFloatingPl += netPl;

            if(hedgeLevel > maxActiveHedgeLevel)
                maxActiveHedgeLevel = hedgeLevel;
            if(cycleNum > maxActiveHedgeCycle)
                maxActiveHedgeCycle = cycleNum;

            bool chainSeen = false;
            for(int ci = 0; ci < ArraySize(seenChainIds); ci++)
            {
                if(seenChainIds[ci] == chainId)
                {
                    chainSeen = true;
                    break;
                }
            }

            if(!chainSeen)
            {
                int newSize = ArraySize(seenChainIds) + 1;
                ArrayResize(seenChainIds, newSize);
                seenChainIds[newSize - 1] = chainId;
                activeHedgeChainCount++;
            }
        }

        double signedDistancePoints = 0.0;
        if(_Point > 0.0)
        {
            if(posType == POSITION_TYPE_BUY)
                signedDistancePoints =
                    (currentPrice - entryPrice) / _Point;
            else
                signedDistancePoints =
                    (entryPrice - currentPrice) / _Point;
        }

        if(strategyPositionCount > 1)
            positionsJson += ",";

        positionsJson += "{";
        positionsJson += "\"ticket\":" + IntegerToString((long)ticket) + ",";
        positionsJson += "\"type\":\"" + (posType == POSITION_TYPE_BUY ? "BUY" : "SELL") + "\",";
        positionsJson += "\"volume\":" + DoubleToString(volume, 4) + ",";
        positionsJson += "\"entry_price\":" + DoubleToString(entryPrice, _Digits) + ",";
        positionsJson += "\"current_price\":" + DoubleToString(currentPrice, _Digits) + ",";
        positionsJson += "\"sl\":" + DoubleToString(sl, _Digits) + ",";
        positionsJson += "\"tp\":" + DoubleToString(tp, _Digits) + ",";
        positionsJson += "\"profit\":" + DoubleToString(profit, 2) + ",";
        positionsJson += "\"swap\":" + DoubleToString(swap, 2) + ",";
        positionsJson += "\"net_pl\":" + DoubleToString(netPl, 2) + ",";
        positionsJson += "\"notional_exposure\":" + DoubleToString(notional, 2) + ",";
        positionsJson += "\"signed_distance_points\":" + DoubleToString(signedDistancePoints, 2) + ",";
        positionsJson += "\"opened_at_epoch\":" + IntegerToString((long)positionTime) + ",";
        positionsJson += "\"age_seconds\":" + IntegerToString((long)MathMax(0, (long)TimeTradeServer() - (long)positionTime)) + ",";
        positionsJson += "\"managed\":" + (managedIndex >= 0 ? "true" : "false") + ",";
        positionsJson += "\"entry_signal_score\":" + DoubleToString(managedSignalScore, 4) + ",";
        positionsJson += "\"partial_close_level\":" + IntegerToString(partialCloseLevel) + ",";
        positionsJson += "\"break_even_locked\":" + (breakEvenLocked ? "true" : "false") + ",";
        positionsJson += "\"chain_id\":" + IntegerToString((long)chainId) + ",";
        positionsJson += "\"hedge_level\":" + IntegerToString(hedgeLevel) + ",";
        positionsJson += "\"cycle_num\":" + IntegerToString(cycleNum) + ",";
        positionsJson += "\"no_rehedge\":" + (noRehedge ? "true" : "false") + ",";
        positionsJson += "\"hedge_graduated\":" + (hedgeGraduated ? "true" : "false") + ",";
        positionsJson += "\"hedge_lock_profit\":" + DoubleToString(hedgeLockProfit, 2);
        positionsJson += "}";
    }

    positionsJson += "]";

    int workingLimitOrders = CountWorkingLimitOrders();

    double basketFloatingPl = GetBasketFloatingPL();
    double basketLossPct =
        (basketFloatingPl < 0.0 && equity > 0.0)
            ? (-basketFloatingPl / equity) * 100.0
            : 0.0;

    double basketRiskRemainingPct =
        (atlasRuntime.enableBasketStop &&
         atlasRuntime.maxBasketLossPct > 0.0)
            ? MathMax(0.0, atlasRuntime.maxBasketLossPct - basketLossPct)
            : 0.0;

    double hedgeChainLossPct =
        (hedgeChainFloatingPl < 0.0 && equity > 0.0)
            ? (-hedgeChainFloatingPl / equity) * 100.0
            : 0.0;

    string json = "{";
    json += "\"connected\":true,";
    json += "\"strategy\":\"nyao\",";
    json += "\"symbol\":\"" + AtlasJsonEscape(_Symbol) + "\",";

    json += "\"balance\":" + DoubleToString(balance, 2) + ",";
    json += "\"equity\":" + DoubleToString(equity, 2) + ",";
    json += "\"floating_profit\":" + DoubleToString(floatingProfit, 2) + ",";
    json += "\"account_margin\":" + DoubleToString(accountMargin, 2) + ",";
    json += "\"free_margin\":" + DoubleToString(freeMargin, 2) + ",";
    json += "\"margin_level_pct\":" + DoubleToString(marginLevel, 2) + ",";
    json += "\"account_leverage\":" + IntegerToString(accountLeverage) + ",";
    json += "\"peak_equity\":" + DoubleToString(peakEquity, 2) + ",";
    json += "\"equity_drawdown_usd\":" + DoubleToString(equityDrawdownUsd, 2) + ",";
    json += "\"equity_drawdown_pct\":" + DoubleToString(equityDrawdownPct, 4) + ",";

    json += "\"open_positions\":" + IntegerToString(PositionsTotal()) + ",";
    json += "\"strategy_open_positions\":" + IntegerToString(strategyPositionCount) + ",";
    json += "\"buy_positions\":" + IntegerToString(buyPositionCount) + ",";
    json += "\"sell_positions\":" + IntegerToString(sellPositionCount) + ",";
    json += "\"winning_positions\":" + IntegerToString(winningPositionCount) + ",";
    json += "\"losing_positions\":" + IntegerToString(losingPositionCount) + ",";
    json += "\"working_limit_orders\":" + IntegerToString(workingLimitOrders) + ",";
    json += "\"total_lots\":" + DoubleToString(totalLots, 4) + ",";
    json += "\"buy_lots\":" + DoubleToString(buyLots, 4) + ",";
    json += "\"sell_lots\":" + DoubleToString(sellLots, 4) + ",";
    json += "\"strategy_floating_pl\":" + DoubleToString(strategyFloatingPl, 2) + ",";
    json += "\"strategy_swap\":" + DoubleToString(strategySwap, 2) + ",";
    json += "\"gross_floating_profit\":" + DoubleToString(grossFloatingProfit, 2) + ",";
    json += "\"gross_floating_loss\":" + DoubleToString(grossFloatingLoss, 2) + ",";
    json += "\"largest_winning_position\":" + DoubleToString(largestWinningPosition, 2) + ",";
    json += "\"largest_losing_position\":" + DoubleToString(largestLosingPosition, 2) + ",";
    json += "\"gross_notional_exposure\":" + DoubleToString(grossNotionalExposure, 2) + ",";
    json += "\"buy_notional_exposure\":" + DoubleToString(buyNotionalExposure, 2) + ",";
    json += "\"sell_notional_exposure\":" + DoubleToString(sellNotionalExposure, 2) + ",";
    json += "\"positions\":" + positionsJson + ",";

    json += "\"active_hedge_chains\":" + IntegerToString(activeHedgeChainCount) + ",";
    json += "\"hedge_chain_positions\":" + IntegerToString(hedgeChainPositionCount) + ",";
    json += "\"hedge_chain_lots\":" + DoubleToString(hedgeChainLots, 4) + ",";
    json += "\"hedge_chain_floating_pl\":" + DoubleToString(hedgeChainFloatingPl, 2) + ",";
    json += "\"hedge_chain_loss_pct\":" + DoubleToString(hedgeChainLossPct, 4) + ",";
    json += "\"max_active_hedge_level\":" + IntegerToString(maxActiveHedgeLevel) + ",";
    json += "\"max_active_hedge_cycle\":" + IntegerToString(maxActiveHedgeCycle) + ",";

    json += "\"basket_floating_pl\":" + DoubleToString(basketFloatingPl, 2) + ",";
    json += "\"basket_loss_pct\":" + DoubleToString(basketLossPct, 4) + ",";
    json += "\"basket_risk_remaining_pct\":" + DoubleToString(basketRiskRemainingPct, 4) + ",";

    json += "\"bid\":" + DoubleToString(bid, _Digits) + ",";
    json += "\"ask\":" + DoubleToString(ask, _Digits) + ",";
    json += "\"spread_points\":" + DoubleToString(spreadPoints, 2) + ",";
    json += "\"effective_spread_cap_points\":" + DoubleToString(effectiveSpreadCapPoints, 2) + ",";
    json += "\"spread_within_limit\":" + (spreadWithinLimit ? "true" : "false") + ",";
    json += "\"current_atr\":" + DoubleToString(currentAtr, _Digits) + ",";
    json += "\"average_atr\":" + DoubleToString(averageAtr, _Digits) + ",";
    json += "\"atr_points\":" + DoubleToString(atrPoints, 2) + ",";
    json += "\"volatility_ratio\":" + DoubleToString(volatilityRatio, 4) + ",";
    json += "\"trading_paused\":" + (isPaused ? "true" : "false") + ",";
    json += "\"pause_until_epoch\":" + IntegerToString(pauseUntilEpoch) + ",";
    json += "\"pause_duration_minutes\":" + IntegerToString(currentPauseDuration) + ",";
    json += "\"total_pause_count\":" + IntegerToString(totalPauseCount) + ",";
    json += "\"total_pause_duration_minutes\":" + DoubleToString(totalPauseDurationMinutes, 2) + ",";
    json += "\"outside_trading_hours\":" + (isOutsideTradingHours ? "true" : "false") + ",";
    json += "\"near_market_close\":" + (isNearMarketClose ? "true" : "false") + ",";
    json += "\"leverage_changed\":" + (isLeverageDiffFromInitial ? "true" : "false") + ",";
    json += "\"initial_leverage\":" + IntegerToString(initialLeverage) + ",";

    json += "\"signal_telemetry_ready\":" + (signalTelemetryReady ? "true" : "false") + ",";
    json += "\"buy_score\":" + DoubleToString(buyScore, 4) + ",";
    json += "\"sell_score\":" + DoubleToString(sellScore, 4) + ",";

    json += "\"buy_trend_score\":" + DoubleToString(buyStrength.trendScore, 4) + ",";
    json += "\"buy_momentum_score\":" + DoubleToString(buyStrength.momentumScore, 4) + ",";
    json += "\"buy_chop_score\":" + DoubleToString(buyStrength.chopScore, 4) + ",";
    json += "\"buy_peak_score\":" + DoubleToString(buyStrength.peakScore, 4) + ",";
    json += "\"buy_volatility_score\":" + DoubleToString(buyStrength.volatilityScore, 4) + ",";
    json += "\"buy_impulse_strength\":" + DoubleToString(buyStrength.impulseStrength, 4) + ",";
    json += "\"buy_velocity\":" + DoubleToString(buyStrength.velocity, 4) + ",";
    json += "\"buy_normalized_velocity\":" + DoubleToString(buyStrength.normalizedVelocity, 4) + ",";
    json += "\"buy_body_ratio\":" + DoubleToString(buyStrength.ratio, 4) + ",";
    json += "\"buy_wick_rejection\":" + DoubleToString(buyStrength.rejection, 4) + ",";
    json += "\"buy_body_penalty\":" + DoubleToString(buyStrength.penaltyBody, 4) + ",";
    json += "\"buy_wick_penalty\":" + DoubleToString(buyStrength.penaltyWick, 4) + ",";
    json += "\"buy_signal_reasoning\":\"" + AtlasJsonEscape(buyStrength.reasoning) + "\",";

    json += "\"sell_trend_score\":" + DoubleToString(sellStrength.trendScore, 4) + ",";
    json += "\"sell_momentum_score\":" + DoubleToString(sellStrength.momentumScore, 4) + ",";
    json += "\"sell_chop_score\":" + DoubleToString(sellStrength.chopScore, 4) + ",";
    json += "\"sell_peak_score\":" + DoubleToString(sellStrength.peakScore, 4) + ",";
    json += "\"sell_volatility_score\":" + DoubleToString(sellStrength.volatilityScore, 4) + ",";
    json += "\"sell_impulse_strength\":" + DoubleToString(sellStrength.impulseStrength, 4) + ",";
    json += "\"sell_velocity\":" + DoubleToString(sellStrength.velocity, 4) + ",";
    json += "\"sell_normalized_velocity\":" + DoubleToString(sellStrength.normalizedVelocity, 4) + ",";
    json += "\"sell_body_ratio\":" + DoubleToString(sellStrength.ratio, 4) + ",";
    json += "\"sell_wick_rejection\":" + DoubleToString(sellStrength.rejection, 4) + ",";
    json += "\"sell_body_penalty\":" + DoubleToString(sellStrength.penaltyBody, 4) + ",";
    json += "\"sell_wick_penalty\":" + DoubleToString(sellStrength.penaltyWick, 4) + ",";
    json += "\"sell_signal_reasoning\":\"" + AtlasJsonEscape(sellStrength.reasoning) + "\",";

    json += "\"atlas_enabled\":" + (atlasEnabled ? "true" : "false") + ",";
    json += "\"atlas_buy_enabled\":" + (atlasBuyEnabled ? "true" : "false") + ",";
    json += "\"atlas_sell_enabled\":" + (atlasSellEnabled ? "true" : "false") + ",";
    json += "\"applied_command_version\":" + IntegerToString(atlasLastCommandVersion) + ",";
    json += "\"structural_config_dirty\":" + (atlasStructuralConfigDirty ? "true" : "false") + ",";
    json += "\"last_global_block_reason\":\"" + AtlasJsonEscape(atlasLastGlobalBlockReason) + "\",";
    json += "\"runtime_directional_body_lookback\":" + IntegerToString(atlasRuntime.directionalBodyLookback) + ",";
    json += "\"runtime_ema_fast_period\":" + IntegerToString(atlasRuntime.emaFastPeriod) + ",";
    json += "\"runtime_ema_slow_period\":" + IntegerToString(atlasRuntime.emaSlowPeriod) + ",";
    json += "\"runtime_slope_lookback\":" + IntegerToString(atlasRuntime.slopeLookback) + ",";
    json += "\"runtime_rsi_period\":" + IntegerToString(atlasRuntime.rsiPeriod) + ",";
    json += "\"runtime_atr_period\":" + IntegerToString(atlasRuntime.atrPeriod) + ",";
    json += "\"runtime_atr_avg_lookback\":" + IntegerToString(atlasRuntime.atrAvgLookback) + ",";
    json += "\"runtime_min_vol_ratio_to_trade\":" + DoubleToString(atlasRuntime.minVolRatioToTrade, 8) + ",";
    json += "\"runtime_impulse_lookback\":" + IntegerToString(atlasRuntime.impulseLookback) + ",";
    json += "\"runtime_impulse_boost_weight\":" + DoubleToString(atlasRuntime.impulseBoostWeight, 8) + ",";
    json += "\"runtime_signal_smoothing_candles\":" + IntegerToString(atlasRuntime.signalSmoothingCandles) + ",";
    json += "\"runtime_current_candle_blend\":" + DoubleToString(atlasRuntime.currentCandleBlend, 8) + ",";
    json += "\"runtime_velocity_window\":" + DoubleToString(atlasRuntime.velocityWindow, 8) + ",";
    json += "\"runtime_rsi_overbought\":" + IntegerToString(atlasRuntime.rsiOverbought) + ",";
    json += "\"runtime_rsi_oversold\":" + IntegerToString(atlasRuntime.rsiOversold) + ",";
    json += "\"runtime_rsi_momentum_buy\":" + IntegerToString(atlasRuntime.rsiMomentumBuy) + ",";
    json += "\"runtime_rsi_momentum_sell\":" + IntegerToString(atlasRuntime.rsiMomentumSell) + ",";
    json += "\"runtime_trend_weight\":" + DoubleToString(atlasRuntime.trendWeight, 8) + ",";
    json += "\"runtime_slope_weight\":" + DoubleToString(atlasRuntime.slopeWeight, 8) + ",";
    json += "\"runtime_momentum_base_weight\":" + DoubleToString(atlasRuntime.momentumBaseWeight, 8) + ",";
    json += "\"runtime_momentum_trigger_weight\":" + DoubleToString(atlasRuntime.momentumTriggerWeight, 8) + ",";
    json += "\"runtime_body_momentum_weight\":" + DoubleToString(atlasRuntime.bodyMomentumWeight, 8) + ",";
    json += "\"runtime_chop_score_high\":" + DoubleToString(atlasRuntime.chopScoreHigh, 8) + ",";
    json += "\"runtime_chop_score_med\":" + DoubleToString(atlasRuntime.chopScoreMed, 8) + ",";
    json += "\"runtime_chop_score_low\":" + DoubleToString(atlasRuntime.chopScoreLow, 8) + ",";
    json += "\"runtime_volatility_score_high\":" + DoubleToString(atlasRuntime.volatilityScoreHigh, 8) + ",";
    json += "\"runtime_volatility_score_low\":" + DoubleToString(atlasRuntime.volatilityScoreLow, 8) + ",";
    json += "\"runtime_peak_score_weight\":" + DoubleToString(atlasRuntime.peakScoreWeight, 8) + ",";
    json += "\"runtime_wick_rejection_weight\":" + DoubleToString(atlasRuntime.wickRejectionWeight, 8) + ",";
    json += "\"runtime_min_body_ratio\":" + DoubleToString(atlasRuntime.minBodyRatio, 8) + ",";
    json += "\"runtime_enable_buy_orders\":" + (atlasRuntime.enableBuyOrders ? "true" : "false") + ",";
    json += "\"runtime_enable_sell_orders\":" + (atlasRuntime.enableSellOrders ? "true" : "false") + ",";
    json += "\"runtime_enable_new_bar_entry_only\":" + (atlasRuntime.enableNewBarEntryOnly ? "true" : "false") + ",";
    json += "\"runtime_enable_max_spread_filter\":" + (atlasRuntime.enableMaxSpreadFilter ? "true" : "false") + ",";
    json += "\"runtime_max_spread_points\":" + DoubleToString(atlasRuntime.maxSpreadPoints, 8) + ",";
    json += "\"runtime_max_spread_atr_ratio\":" + DoubleToString(atlasRuntime.maxSpreadAtrRatio, 8) + ",";
    json += "\"runtime_base_lot_size\":" + DoubleToString(atlasRuntime.baseLotSize, 8) + ",";
    json += "\"runtime_max_open_orders\":" + IntegerToString(atlasRuntime.maxOpenOrders) + ",";
    json += "\"runtime_max_trades_per_candle\":" + IntegerToString(atlasRuntime.maxTradesPerCandle) + ",";
    json += "\"runtime_consecutive_candle_threshold_boost\":" + DoubleToString(atlasRuntime.consecutiveCandleThresholdBoost, 8) + ",";
    json += "\"runtime_max_consecutive_candle_boosts\":" + IntegerToString(atlasRuntime.maxConsecutiveCandleBoosts) + ",";
    json += "\"runtime_zone_points\":" + DoubleToString(atlasRuntime.zonePoints, 8) + ",";
    json += "\"runtime_buy_duplicate_multiplier\":" + DoubleToString(atlasRuntime.buyDuplicateMultiplier, 8) + ",";
    json += "\"runtime_sell_duplicate_multiplier\":" + DoubleToString(atlasRuntime.sellDuplicateMultiplier, 8) + ",";
    json += "\"runtime_min_break_even_profit\":" + DoubleToString(atlasRuntime.minBreakEvenProfit, 8) + ",";
    json += "\"runtime_profit_threshold_multiplier\":" + DoubleToString(atlasRuntime.profitThresholdMultiplier, 8) + ",";
    json += "\"runtime_loss_threshold_multiplier\":" + DoubleToString(atlasRuntime.lossThresholdMultiplier, 8) + ",";
    json += "\"runtime_min_buy_signal_score\":" + DoubleToString(atlasRuntime.minBuySignalScore, 8) + ",";
    json += "\"runtime_min_sell_signal_score\":" + DoubleToString(atlasRuntime.minSellSignalScore, 8) + ",";
    json += "\"runtime_enable_limit_entry\":" + (atlasRuntime.enableLimitEntry ? "true" : "false") + ",";
    json += "\"runtime_limit_entry_anchor\":" + IntegerToString((int)atlasRuntime.limitEntryAnchor) + ",";
    json += "\"runtime_limit_entry_atr_fraction\":" + DoubleToString(atlasRuntime.limitEntryAtrFraction, 8) + ",";
    json += "\"runtime_limit_entry_expiry_bars\":" + IntegerToString(atlasRuntime.limitEntryExpiryBars) + ",";
    json += "\"runtime_limit_entry_cancel_on_flip\":" + (atlasRuntime.limitEntryCancelOnFlip ? "true" : "false") + ",";
    json += "\"runtime_enable_signal_dampening\":" + (atlasRuntime.enableSignalDampening ? "true" : "false") + ",";
    json += "\"runtime_max_losing_positions_same_dir\":" + IntegerToString(atlasRuntime.maxLosingPositionsSameDir) + ",";
    json += "\"runtime_losing_pos_score_penalty\":" + DoubleToString(atlasRuntime.losingPosScorePenalty, 8) + ",";
    json += "\"runtime_drawdown_threshold_pct\":" + DoubleToString(atlasRuntime.drawdownThresholdPct, 8) + ",";
    json += "\"runtime_drawdown_score_boost\":" + DoubleToString(atlasRuntime.drawdownScoreBoost, 8) + ",";
    json += "\"runtime_consecutive_losses_before_cooldown\":" + IntegerToString(atlasRuntime.consecutiveLossesBeforeCooldown) + ",";
    json += "\"runtime_consecutive_loss_cooldown_bars\":" + IntegerToString(atlasRuntime.consecutiveLossCooldownBars) + ",";
    json += "\"runtime_enable_loss_management\":" + (atlasRuntime.enableLossManagement ? "true" : "false") + ",";
    json += "\"runtime_max_holding_loss_positions\":" + IntegerToString(atlasRuntime.maxHoldingLossPositions) + ",";
    json += "\"runtime_min_health_score\":" + DoubleToString(atlasRuntime.minHealthScore, 8) + ",";
    json += "\"runtime_max_adverse_atr\":" + DoubleToString(atlasRuntime.maxAdverseAtr, 8) + ",";
    json += "\"runtime_health_trend_weight\":" + DoubleToString(atlasRuntime.healthTrendWeight, 8) + ",";
    json += "\"runtime_health_rsi_weight\":" + DoubleToString(atlasRuntime.healthRsiWeight, 8) + ",";
    json += "\"runtime_health_atr_weight\":" + DoubleToString(atlasRuntime.healthAtrWeight, 8) + ",";
    json += "\"runtime_health_swing_weight\":" + DoubleToString(atlasRuntime.healthSwingWeight, 8) + ",";
    json += "\"runtime_health_rsi_buy_min\":" + DoubleToString(atlasRuntime.healthRsiBuyMin, 8) + ",";
    json += "\"runtime_health_rsi_sell_max\":" + DoubleToString(atlasRuntime.healthRsiSellMax, 8) + ",";
    json += "\"runtime_health_swing_lookback\":" + IntegerToString(atlasRuntime.healthSwingLookback) + ",";
    json += "\"runtime_health_grace_bars\":" + IntegerToString(atlasRuntime.healthGraceBars) + ",";
    json += "\"runtime_enable_partial_close\":" + (atlasRuntime.enablePartialClose ? "true" : "false") + ",";
    json += "\"runtime_partial_close75_pct\":" + DoubleToString(atlasRuntime.partialClose75Pct, 8) + ",";
    json += "\"runtime_partial_close50_pct\":" + DoubleToString(atlasRuntime.partialClose50Pct, 8) + ",";
    json += "\"runtime_partial_close25_pct\":" + DoubleToString(atlasRuntime.partialClose25Pct, 8) + ",";
    json += "\"runtime_enable_health_sl_tightening\":" + (atlasRuntime.enableHealthSlTightening ? "true" : "false") + ",";
    json += "\"runtime_sl_tighten_atr_multiplier\":" + DoubleToString(atlasRuntime.slTightenAtrMultiplier, 8) + ",";
    json += "\"runtime_sl_tighten_min_health_pct\":" + DoubleToString(atlasRuntime.slTightenMinHealthPct, 8) + ",";
    json += "\"runtime_enable_break_even_on_spread\":" + (atlasRuntime.enableBreakEvenOnSpread ? "true" : "false") + ",";
    json += "\"runtime_break_even_spread_multiplier\":" + DoubleToString(atlasRuntime.breakEvenSpreadMultiplier, 8) + ",";
    json += "\"runtime_enable_virtual_sl_reentry\":" + (atlasRuntime.enableVirtualSlReentry ? "true" : "false") + ",";
    json += "\"runtime_reentry_respects_new_bar_gate\":" + (atlasRuntime.reentryRespectsNewBarGate ? "true" : "false") + ",";
    json += "\"runtime_reentry_min_signal_pct\":" + DoubleToString(atlasRuntime.reentryMinSignalPct, 8) + ",";
    json += "\"runtime_enable_profit_offset_sl\":" + (atlasRuntime.enableProfitOffsetSl ? "true" : "false") + ",";
    json += "\"runtime_consecutive_wins_required\":" + IntegerToString(atlasRuntime.consecutiveWinsRequired) + ",";
    json += "\"runtime_min_offset_profit\":" + DoubleToString(atlasRuntime.minOffsetProfit, 8) + ",";
    json += "\"runtime_enable_hedge_chain\":" + (atlasRuntime.enableHedgeChain ? "true" : "false") + ",";
    json += "\"runtime_hedge_trigger_atr\":" + DoubleToString(atlasRuntime.hedgeTriggerAtr, 8) + ",";
    json += "\"runtime_hedge_require_signal\":" + (atlasRuntime.hedgeRequireSignal ? "true" : "false") + ",";
    json += "\"runtime_hedge_min_signal_score\":" + DoubleToString(atlasRuntime.hedgeMinSignalScore, 8) + ",";
    json += "\"runtime_hedge_auto_lot\":" + (atlasRuntime.hedgeAutoLot ? "true" : "false") + ",";
    json += "\"runtime_hedge_recovery_atr\":" + DoubleToString(atlasRuntime.hedgeRecoveryAtr, 8) + ",";
    json += "\"runtime_hedge_lot_multiplier\":" + DoubleToString(atlasRuntime.hedgeLotMultiplier, 8) + ",";
    json += "\"runtime_hedge_max_lot\":" + DoubleToString(atlasRuntime.hedgeMaxLot, 8) + ",";
    json += "\"runtime_hedge_recovery_pct\":" + DoubleToString(atlasRuntime.hedgeRecoveryPct, 8) + ",";
    json += "\"runtime_hedge_roll_min_profit\":" + DoubleToString(atlasRuntime.hedgeRollMinProfit, 8) + ",";
    json += "\"runtime_hedge_cycle_levels\":" + IntegerToString(atlasRuntime.hedgeCycleLevels) + ",";
    json += "\"runtime_enable_hedge_cycle_reset\":" + (atlasRuntime.enableHedgeCycleReset ? "true" : "false") + ",";
    json += "\"runtime_hedge_cycle_partial_pct\":" + DoubleToString(atlasRuntime.hedgeCyclePartialPct, 8) + ",";
    json += "\"runtime_hedge_max_cycles\":" + IntegerToString(atlasRuntime.hedgeMaxCycles) + ",";
    json += "\"runtime_hedge_max_chain_loss_usd\":" + DoubleToString(atlasRuntime.hedgeMaxChainLossUsd, 8) + ",";
    json += "\"runtime_hedge_max_chain_loss_pct\":" + DoubleToString(atlasRuntime.hedgeMaxChainLossPct, 8) + ",";
    json += "\"runtime_hedge_clear_root_sl\":" + (atlasRuntime.hedgeClearRootSl ? "true" : "false") + ",";
    json += "\"runtime_hedge_trail_atr\":" + DoubleToString(atlasRuntime.hedgeTrailAtr, 8) + ",";
    json += "\"runtime_enable_dynamic_lots\":" + (atlasRuntime.enableDynamicLots ? "true" : "false") + ",";
    json += "\"runtime_equity_drop_percent\":" + DoubleToString(atlasRuntime.equityDropPercent, 8) + ",";
    json += "\"runtime_max_equity_drop_lot_steps\":" + IntegerToString(atlasRuntime.maxEquityDropLotSteps) + ",";
    json += "\"runtime_min_signal_strength_for_lot\":" + DoubleToString(atlasRuntime.minSignalStrengthForLot, 8) + ",";
    json += "\"runtime_lot_step_size\":" + DoubleToString(atlasRuntime.lotStepSize, 8) + ",";
    json += "\"runtime_max_lot_size\":" + DoubleToString(atlasRuntime.maxLotSize, 8) + ",";
    json += "\"runtime_enable_basket_stop\":" + (atlasRuntime.enableBasketStop ? "true" : "false") + ",";
    json += "\"runtime_max_basket_loss_pct\":" + DoubleToString(atlasRuntime.maxBasketLossPct, 8) + ",";
    json += "\"runtime_min_equity_percent\":" + DoubleToString(atlasRuntime.minEquityPercent, 8) + ",";
    json += "\"runtime_max_drawdown_from_peak\":" + DoubleToString(atlasRuntime.maxDrawdownFromPeak, 8) + ",";
    json += "\"runtime_pause_minutes\":" + IntegerToString(atlasRuntime.pauseMinutes) + ",";
    json += "\"runtime_pause_minutes_multiplier\":" + DoubleToString(atlasRuntime.pauseMinutesMultiplier, 8) + ",";
    json += "\"runtime_max_pause_minutes\":" + IntegerToString(atlasRuntime.maxPauseMinutes) + ",";
    json += "\"runtime_max_min_equity_triggers\":" + IntegerToString(atlasRuntime.maxMinEquityTriggers) + ",";
    json += "\"runtime_reset_on_new_peak\":" + (atlasRuntime.resetOnNewPeak ? "true" : "false") + ",";
    json += "\"runtime_target_equity\":" + DoubleToString(atlasRuntime.targetEquity, 8) + ",";
    json += "\"runtime_minimum_equity\":" + DoubleToString(atlasRuntime.minimumEquity, 8) + ",";
    json += "\"runtime_enable_take_profit\":" + (atlasRuntime.enableTakeProfit ? "true" : "false") + ",";
    json += "\"runtime_tp_input_type\":" + IntegerToString((int)atlasRuntime.tpInputType) + ",";
    json += "\"runtime_tp_value\":" + DoubleToString(atlasRuntime.tpValue, 8) + ",";
    json += "\"runtime_enable_stop_loss\":" + (atlasRuntime.enableStopLoss ? "true" : "false") + ",";
    json += "\"runtime_sl_input_type\":" + IntegerToString((int)atlasRuntime.slInputType) + ",";
    json += "\"runtime_sl_value\":" + DoubleToString(atlasRuntime.slValue, 8) + ",";
    json += "\"runtime_enable_risk_reward\":" + (atlasRuntime.enableRiskReward ? "true" : "false") + ",";
    json += "\"runtime_rr_risk_mode\":" + IntegerToString((int)atlasRuntime.rrRiskMode) + ",";
    json += "\"runtime_rr_risk_input_type\":" + IntegerToString((int)atlasRuntime.rrRiskInputType) + ",";
    json += "\"runtime_rr_risk_value\":" + DoubleToString(atlasRuntime.rrRiskValue, 8) + ",";
    json += "\"runtime_rr_atr_multiplier\":" + DoubleToString(atlasRuntime.rrAtrMultiplier, 8) + ",";
    json += "\"runtime_risk_reward_ratio\":" + DoubleToString(atlasRuntime.riskRewardRatio, 8) + ",";
    json += "\"runtime_enable_trailing\":" + (atlasRuntime.enableTrailing ? "true" : "false") + ",";
    json += "\"runtime_trailing_enable_break_even_lock\":" + (atlasRuntime.trailingEnableBreakEvenLock ? "true" : "false") + ",";
    json += "\"runtime_trailing_sl_on_profitable_only\":" + (atlasRuntime.trailingSlOnProfitableOnly ? "true" : "false") + ",";
    json += "\"runtime_enable_adaptive_tp\":" + (atlasRuntime.enableAdaptiveTp ? "true" : "false") + ",";
    json += "\"runtime_enable_adaptive_sl\":" + (atlasRuntime.enableAdaptiveSl ? "true" : "false") + ",";
    json += "\"runtime_ts_input_type\":" + IntegerToString((int)atlasRuntime.tsInputType) + ",";
    json += "\"runtime_trailing_distance_value\":" + DoubleToString(atlasRuntime.trailingDistanceValue, 8) + ",";
    json += "\"runtime_trailing_value_multiplier\":" + DoubleToString(atlasRuntime.trailingValueMultiplier, 8) + ",";
    json += "\"runtime_enable_discord_alerts\":" + (atlasRuntime.enableDiscordAlerts ? "true" : "false") + ",";
    json += "\"runtime_enable_trading_hours\":" + (atlasRuntime.enableTradingHours ? "true" : "false") + ",";
    json += "\"runtime_trading_start_time\":\"" + atlasRuntime.tradingStartTime + "\",";
    json += "\"runtime_trading_end_time\":\"" + atlasRuntime.tradingEndTime + "\",";
    json += "\"runtime_enable_reports\":" + (atlasRuntime.enableReports ? "true" : "false") + ",";
    json += "\"runtime_send_report_every_hour\":" + IntegerToString(atlasRuntime.sendReportEveryHour) + ",";
    json += "\"runtime_enable_market_close_filter\":" + (atlasRuntime.enableMarketCloseFilter ? "true" : "false") + ",";
    json += "\"runtime_minutes_before_close\":" + IntegerToString(atlasRuntime.minutesBeforeClose) + ",";
    json += "\"runtime_enable_news_filter\":" + (atlasRuntime.enableNewsFilter ? "true" : "false") + ",";
    json += "\"runtime_news_minutes_before\":" + IntegerToString(atlasRuntime.newsMinutesBefore) + ",";
    json += "\"runtime_news_minutes_after\":" + IntegerToString(atlasRuntime.newsMinutesAfter) + ",";
    json += "\"runtime_enable_leverage_pause\":" + (atlasRuntime.enableLeveragePause ? "true" : "false") + ",";
    json += "\"runtime_enable_logging\":" + (atlasRuntime.enableLogging ? "true" : "false") + ",";

    json += "\"buy_adjusted_score\":" + DoubleToString(atlasBuyAdjustedScore, 4) + ",";
    json += "\"sell_adjusted_score\":" + DoubleToString(atlasSellAdjustedScore, 4) + ",";
    json += "\"buy_effective_threshold\":" + DoubleToString(atlasBuyEffectiveThreshold, 4) + ",";
    json += "\"sell_effective_threshold\":" + DoubleToString(atlasSellEffectiveThreshold, 4) + ",";
    json += "\"buy_entry_eligible\":" + (atlasBuyEntryEligible ? "true" : "false") + ",";
    json += "\"sell_entry_eligible\":" + (atlasSellEntryEligible ? "true" : "false") + ",";
    json += "\"buy_block_reason\":\"" + AtlasJsonEscape(atlasBuyBlockReason) + "\",";
    json += "\"sell_block_reason\":\"" + AtlasJsonEscape(atlasSellBlockReason) + "\",";
    json += "\"new_bar_entry_only\":" + (atlasRuntime.enableNewBarEntryOnly ? "true" : "false") + ",";
    json += "\"new_bar_ready\":" + (atlasNewBarReady ? "true" : "false") + ",";
    json += "\"cooldown_active\":" + (atlasCooldownActive ? "true" : "false") + ",";
    json += "\"cooldown_until_epoch\":" + IntegerToString((long)cooldownUntilBarTime) + ",";

    json += "\"last_order_attempted\":" + (atlasLastOrderAttempted ? "true" : "false") + ",";
    json += "\"last_order_success\":" + (atlasLastOrderSuccess ? "true" : "false") + ",";
    json += "\"last_order_direction\":\"" + AtlasJsonEscape(atlasLastOrderDirection) + "\",";
    json += "\"last_order_mode\":\"" + AtlasJsonEscape(atlasLastOrderMode) + "\",";
    json += "\"last_order_retcode\":" + IntegerToString(atlasLastOrderRetcode) + ",";
    json += "\"last_order_ticket\":" + IntegerToString((long)atlasLastOrderTicket) + ",";
    json += "\"last_order_time_epoch\":" + IntegerToString((long)atlasLastOrderTime) + ",";
    json += "\"timestamp\":\"" + atlasTimestamp + "\"";
    json += "}";

    int handle = FileOpen(atlasStatusFile, FILE_WRITE | FILE_TXT | FILE_ANSI);
    if(handle == INVALID_HANDLE)
    {
        Print("Atlas: could not write status file. Error=", GetLastError());
        return;
    }

    FileWriteString(handle, json);
    FileClose(handle);
}



// Candle-based Position Counters
datetime currentBarTime = 0;
int buysOnCurrentBar = 0;
int sellsOnCurrentBar = 0;

// New-Bar Entry Gate (only evaluate entries once per closed bar when enabled)
datetime lastEntryBarTime = 0;

// Consecutive Trading Candle Tracker (for threshold escalation)
int consecutiveBuyCandles = 0;                            // How many consecutive candles opened buy positions
int consecutiveSellCandles = 0;                           // How many consecutive candles opened sell positions
bool prevBarHadBuys = false;                              // Whether the previous bar opened buy positions
bool prevBarHadSells = false;                             // Whether the previous bar opened sell positions

// Signal Dampening Globals
int consecutiveLossCount = 0;                             // Track consecutive closing losses
datetime cooldownUntilBarTime = 0;                        // Bar time after which cooldown expires

// Last Position Tracking
datetime lastBuyTime = 0;
double lastBuyPrice = 0;
datetime lastSellTime = 0;
double lastSellPrice = 0;

// Last signal tracking per candle 
double lastBuySignalScore = 0; 
double lastBuySignalScorePrev = 0; 
double lastBuyVelocity = 0; 
double lastBuyNormalizedVelocity = 0; 

double lastSellSignalScore = 0; 
double lastSellSignalScorePrev = 0; 
double lastSellVelocity = 0; 
double lastSellNormalizedVelocity = 0;

// Per-tick signal cache (invalidated each tick)
bool _buyStrengthValid = false;
bool _sellStrengthValid = false;
SignalStrength _cachedBuyStrength;
SignalStrength _cachedSellStrength;

// Trade Statistics Structure
struct TradeStats
{
    int count;
    int won;
    int lost;
    double profit;                                        // Total net profit
    double loss;                                          // Total net loss (sum of negative profits)
    double avgProfit;                                     // Average of winning trades
    double maxProfit;                                     // Largest single profit
    double minProfit;                                     // Smallest single profit
    double avgLoss;                                       // Average of losing trades
    double maxLoss;                                       // Largest single loss (most negative)
    double minLoss;                                       // Smallest single loss (closest to 0)
};

// +------------------------------------------------------------------+
// | Create Password Dialog                                           |
// +------------------------------------------------------------------+
bool CreatePasswordDialog()
{
    if(!passwordDialog.Create(0, "PasswordDialog", 0, 10, 10, 324, 120))
        return false;
    
    passwordDialog.Caption("Enter Password to Use Nyao Scalper EA");
    
    if(!passwordEdit.Create(0, "PasswordEdit", 0, 5, 10, 300, 35))
        return false;

    passwordEdit.Text("");

    if(!passwordDialog.Add(passwordEdit))
        return false;
    
    if(!passwordSubmitBtn.Create(0, "PasswordSubmit", 0, 5, 45, 100, 75))
        return false;

    passwordSubmitBtn.Text("Submit");

    if(!passwordDialog.Add(passwordSubmitBtn))
        return false;
    
    return true;
}

void InitializeAtlasRuntime()
{
    atlasRuntime.directionalBodyLookback = DirectionalBodyLookback;
    atlasRuntime.emaFastPeriod = EMAFastPeriod;
    atlasRuntime.emaSlowPeriod = EMASlowPeriod;
    atlasRuntime.slopeLookback = SlopeLookback;
    atlasRuntime.rsiPeriod = RSIPeriod;
    atlasRuntime.atrPeriod = ATRPeriod;
    atlasRuntime.atrAvgLookback = ATRAvgLookback;
    atlasRuntime.minVolRatioToTrade = MinVolRatioToTrade;
    atlasRuntime.impulseLookback = ImpulseLookback;
    atlasRuntime.impulseBoostWeight = ImpulseBoostWeight;
    atlasRuntime.signalSmoothingCandles = SignalSmoothingCandles;
    atlasRuntime.currentCandleBlend = CurrentCandleBlend;
    atlasRuntime.velocityWindow = VelocityWindow;
    atlasRuntime.rsiOverbought = RSIOverbought;
    atlasRuntime.rsiOversold = RSIOversold;
    atlasRuntime.rsiMomentumBuy = RSIMomentumBuy;
    atlasRuntime.rsiMomentumSell = RSIMomentumSell;
    atlasRuntime.trendWeight = TrendWeight;
    atlasRuntime.slopeWeight = SlopeWeight;
    atlasRuntime.momentumBaseWeight = MomentumBaseWeight;
    atlasRuntime.momentumTriggerWeight = MomentumTriggerWeight;
    atlasRuntime.bodyMomentumWeight = BodyMomentumWeight;
    atlasRuntime.chopScoreHigh = ChopScoreHigh;
    atlasRuntime.chopScoreMed = ChopScoreMed;
    atlasRuntime.chopScoreLow = ChopScoreLow;
    atlasRuntime.volatilityScoreHigh = VolatilityScoreHigh;
    atlasRuntime.volatilityScoreLow = VolatilityScoreLow;
    atlasRuntime.peakScoreWeight = PeakScoreWeight;
    atlasRuntime.wickRejectionWeight = WickRejectionWeight;
    atlasRuntime.minBodyRatio = MinBodyRatio;
    atlasRuntime.enableBuyOrders = EnableBuyOrders;
    atlasRuntime.enableSellOrders = EnableSellOrders;
    atlasRuntime.enableNewBarEntryOnly = EnableNewBarEntryOnly;
    atlasRuntime.enableMaxSpreadFilter = EnableMaxSpreadFilter;
    atlasRuntime.maxSpreadPoints = MaxSpreadPoints;
    atlasRuntime.maxSpreadAtrRatio = MaxSpreadATRRatio;
    atlasRuntime.baseLotSize = BaseLotSize;
    atlasRuntime.maxOpenOrders = MaxOpenOrders;
    atlasRuntime.maxTradesPerCandle = MaxTradesPerCandle;
    atlasRuntime.consecutiveCandleThresholdBoost = ConsecutiveCandleThresholdBoost;
    atlasRuntime.maxConsecutiveCandleBoosts = MaxConsecutiveCandleBoosts;
    atlasRuntime.zonePoints = ZonePoints;
    atlasRuntime.buyDuplicateMultiplier = BuyDuplicateMultiplier;
    atlasRuntime.sellDuplicateMultiplier = SellDuplicateMultiplier;
    atlasRuntime.minBreakEvenProfit = MinBreakEvenProfit;
    atlasRuntime.profitThresholdMultiplier = ProfitThresholdMultiplier;
    atlasRuntime.lossThresholdMultiplier = LossThresholdMultiplier;
    atlasRuntime.minBuySignalScore = MinBuySignalScore;
    atlasRuntime.minSellSignalScore = MinSellSignalScore;
    atlasRuntime.enableLimitEntry = EnableLimitEntry;
    atlasRuntime.limitEntryAnchor = LimitEntryAnchor;
    atlasRuntime.limitEntryAtrFraction = LimitEntryATRFraction;
    atlasRuntime.limitEntryExpiryBars = LimitEntryExpiryBars;
    atlasRuntime.limitEntryCancelOnFlip = LimitEntryCancelOnFlip;
    atlasRuntime.enableSignalDampening = EnableSignalDampening;
    atlasRuntime.maxLosingPositionsSameDir = MaxLosingPositionsSameDir;
    atlasRuntime.losingPosScorePenalty = LosingPosScorePenalty;
    atlasRuntime.drawdownThresholdPct = DrawdownThresholdPct;
    atlasRuntime.drawdownScoreBoost = DrawdownScoreBoost;
    atlasRuntime.consecutiveLossesBeforeCooldown = ConsecutiveLossesBeforeCooldown;
    atlasRuntime.consecutiveLossCooldownBars = ConsecutiveLossCooldownBars;
    atlasRuntime.enableLossManagement = EnableLossManagement;
    atlasRuntime.maxHoldingLossPositions = MaxHoldingLossPositions;
    atlasRuntime.minHealthScore = MinHealthScore;
    atlasRuntime.maxAdverseAtr = MaxAdverseATR;
    atlasRuntime.healthTrendWeight = HealthTrendWeight;
    atlasRuntime.healthRsiWeight = HealthRSIWeight;
    atlasRuntime.healthAtrWeight = HealthATRWeight;
    atlasRuntime.healthSwingWeight = HealthSwingWeight;
    atlasRuntime.healthRsiBuyMin = HealthRSIBuyMin;
    atlasRuntime.healthRsiSellMax = HealthRSISellMax;
    atlasRuntime.healthSwingLookback = HealthSwingLookback;
    atlasRuntime.healthGraceBars = HealthGraceBars;
    atlasRuntime.enablePartialClose = EnablePartialClose;
    atlasRuntime.partialClose75Pct = PartialClose75Pct;
    atlasRuntime.partialClose50Pct = PartialClose50Pct;
    atlasRuntime.partialClose25Pct = PartialClose25Pct;
    atlasRuntime.enableHealthSlTightening = EnableHealthSLTightening;
    atlasRuntime.slTightenAtrMultiplier = SLTightenATRMultiplier;
    atlasRuntime.slTightenMinHealthPct = SLTightenMinHealthPct;
    atlasRuntime.enableBreakEvenOnSpread = EnableBreakEvenOnSpread;
    atlasRuntime.breakEvenSpreadMultiplier = BreakEvenSpreadMultiplier;
    atlasRuntime.enableVirtualSlReentry = EnableVirtualSLReentry;
    atlasRuntime.reentryRespectsNewBarGate = ReentryRespectsNewBarGate;
    atlasRuntime.reentryMinSignalPct = ReentryMinSignalPct;
    atlasRuntime.enableProfitOffsetSl = EnableProfitOffsetSL;
    atlasRuntime.consecutiveWinsRequired = ConsecutiveWinsRequired;
    atlasRuntime.minOffsetProfit = MinOffsetProfit;
    atlasRuntime.enableHedgeChain = EnableHedgeChain;
    atlasRuntime.hedgeTriggerAtr = HedgeTriggerATR;
    atlasRuntime.hedgeRequireSignal = HedgeRequireSignal;
    atlasRuntime.hedgeMinSignalScore = HedgeMinSignalScore;
    atlasRuntime.hedgeAutoLot = HedgeAutoLot;
    atlasRuntime.hedgeRecoveryAtr = HedgeRecoveryATR;
    atlasRuntime.hedgeLotMultiplier = HedgeLotMultiplier;
    atlasRuntime.hedgeMaxLot = HedgeMaxLot;
    atlasRuntime.hedgeRecoveryPct = HedgeRecoveryPct;
    atlasRuntime.hedgeRollMinProfit = HedgeRollMinProfit;
    atlasRuntime.hedgeCycleLevels = HedgeCycleLevels;
    atlasRuntime.enableHedgeCycleReset = EnableHedgeCycleReset;
    atlasRuntime.hedgeCyclePartialPct = HedgeCyclePartialPct;
    atlasRuntime.hedgeMaxCycles = HedgeMaxCycles;
    atlasRuntime.hedgeMaxChainLossUsd = HedgeMaxChainLossUSD;
    atlasRuntime.hedgeMaxChainLossPct = HedgeMaxChainLossPct;
    atlasRuntime.hedgeClearRootSl = HedgeClearRootSL;
    atlasRuntime.hedgeTrailAtr = HedgeTrailATR;
    atlasRuntime.enableDynamicLots = EnableDynamicLots;
    atlasRuntime.equityDropPercent = EquityDropPercent;
    atlasRuntime.maxEquityDropLotSteps = MaxEquityDropLotSteps;
    atlasRuntime.minSignalStrengthForLot = MinSignalStrengthForLot;
    atlasRuntime.lotStepSize = LotStepSize;
    atlasRuntime.maxLotSize = MaxLotSize;
    atlasRuntime.enableBasketStop = EnableBasketStop;
    atlasRuntime.maxBasketLossPct = MaxBasketLossPct;
    atlasRuntime.minEquityPercent = MinEquityPercent;
    atlasRuntime.maxDrawdownFromPeak = MaxDrawdownFromPeak;
    atlasRuntime.pauseMinutes = PauseMinutes;
    atlasRuntime.pauseMinutesMultiplier = PauseMinutesMultiplier;
    atlasRuntime.maxPauseMinutes = MaxPauseMinutes;
    atlasRuntime.maxMinEquityTriggers = MaxMinEquityTriggers;
    atlasRuntime.resetOnNewPeak = ResetOnNewPeak;
    atlasRuntime.targetEquity = TargetEquity;
    atlasRuntime.minimumEquity = MinimumEquity;
    atlasRuntime.enableTakeProfit = EnableTakeProfit;
    atlasRuntime.tpInputType = TPInputType;
    atlasRuntime.tpValue = TPValue;
    atlasRuntime.enableStopLoss = EnableStopLoss;
    atlasRuntime.slInputType = SLInputType;
    atlasRuntime.slValue = SLValue;
    atlasRuntime.enableRiskReward = EnableRiskReward;
    atlasRuntime.rrRiskMode = RRRiskMode;
    atlasRuntime.rrRiskInputType = RRRiskInputType;
    atlasRuntime.rrRiskValue = RRRiskValue;
    atlasRuntime.rrAtrMultiplier = RRAtrMultiplier;
    atlasRuntime.riskRewardRatio = RiskRewardRatio;
    atlasRuntime.enableTrailing = EnableTrailing;
    atlasRuntime.trailingEnableBreakEvenLock = TrailingEnableBreakEvenLock;
    atlasRuntime.trailingSlOnProfitableOnly = TrailingSLOnProfitableOnly;
    atlasRuntime.enableAdaptiveTp = EnableAdaptiveTP;
    atlasRuntime.enableAdaptiveSl = EnableAdaptiveSL;
    atlasRuntime.tsInputType = TSInputType;
    atlasRuntime.trailingDistanceValue = TrailingDistanceValue;
    atlasRuntime.trailingValueMultiplier = TrailingValueMultiplier;
    atlasRuntime.enableDiscordAlerts = EnableDiscordAlerts;
    atlasRuntime.enableTradingHours = EnableTradingHours;
    atlasRuntime.tradingStartTime = TradingStartTime;
    atlasRuntime.tradingEndTime = TradingEndTime;
    atlasRuntime.enableReports = EnableReports;
    atlasRuntime.sendReportEveryHour = SendReportEveryHour;
    atlasRuntime.enableMarketCloseFilter = EnableMarketCloseFilter;
    atlasRuntime.minutesBeforeClose = MinutesBeforeClose;
    atlasRuntime.enableNewsFilter = EnableNewsFilter;
    atlasRuntime.newsMinutesBefore = NewsMinutesBefore;
    atlasRuntime.newsMinutesAfter = NewsMinutesAfter;
    atlasRuntime.enableLeveragePause = EnableLeveragePause;
    atlasRuntime.enableLogging = EnableLogging;

    atlasBuyEnabled = atlasRuntime.enableBuyOrders;
    atlasSellEnabled = atlasRuntime.enableSellOrders;
    atlasBuyEffectiveThreshold = atlasRuntime.minBuySignalScore;
    atlasSellEffectiveThreshold = atlasRuntime.minSellSignalScore;
    atlasBuyBlockReason = "INITIALIZED";
    atlasSellBlockReason = "INITIALIZED";
    atlasRuntimeInitialized = true;

    Print(
        "[ATLAS] Full runtime initialized from Nyao profile. ",
        "BuyThreshold=", DoubleToString(atlasRuntime.minBuySignalScore, 2),
        " SellThreshold=", DoubleToString(atlasRuntime.minSellSignalScore, 2),
        " BaseLot=", DoubleToString(atlasRuntime.baseLotSize, 2),
        " MaxOrders=", atlasRuntime.maxOpenOrders,
        " NewBarOnly=", atlasRuntime.enableNewBarEntryOnly
    );
}

// Effective runtime aliases. The .set file seeds AtlasRuntimeConfig at startup.
#define DirectionalBodyLookback atlasRuntime.directionalBodyLookback
#define EMAFastPeriod atlasRuntime.emaFastPeriod
#define EMASlowPeriod atlasRuntime.emaSlowPeriod
#define SlopeLookback atlasRuntime.slopeLookback
#define RSIPeriod atlasRuntime.rsiPeriod
#define ATRPeriod atlasRuntime.atrPeriod
#define ATRAvgLookback atlasRuntime.atrAvgLookback
#define MinVolRatioToTrade atlasRuntime.minVolRatioToTrade
#define ImpulseLookback atlasRuntime.impulseLookback
#define ImpulseBoostWeight atlasRuntime.impulseBoostWeight
#define SignalSmoothingCandles atlasRuntime.signalSmoothingCandles
#define CurrentCandleBlend atlasRuntime.currentCandleBlend
#define VelocityWindow atlasRuntime.velocityWindow
#define RSIOverbought atlasRuntime.rsiOverbought
#define RSIOversold atlasRuntime.rsiOversold
#define RSIMomentumBuy atlasRuntime.rsiMomentumBuy
#define RSIMomentumSell atlasRuntime.rsiMomentumSell
#define TrendWeight atlasRuntime.trendWeight
#define SlopeWeight atlasRuntime.slopeWeight
#define MomentumBaseWeight atlasRuntime.momentumBaseWeight
#define MomentumTriggerWeight atlasRuntime.momentumTriggerWeight
#define BodyMomentumWeight atlasRuntime.bodyMomentumWeight
#define ChopScoreHigh atlasRuntime.chopScoreHigh
#define ChopScoreMed atlasRuntime.chopScoreMed
#define ChopScoreLow atlasRuntime.chopScoreLow
#define VolatilityScoreHigh atlasRuntime.volatilityScoreHigh
#define VolatilityScoreLow atlasRuntime.volatilityScoreLow
#define PeakScoreWeight atlasRuntime.peakScoreWeight
#define WickRejectionWeight atlasRuntime.wickRejectionWeight
#define MinBodyRatio atlasRuntime.minBodyRatio
#define EnableBuyOrders atlasRuntime.enableBuyOrders
#define EnableSellOrders atlasRuntime.enableSellOrders
#define EnableNewBarEntryOnly atlasRuntime.enableNewBarEntryOnly
#define EnableMaxSpreadFilter atlasRuntime.enableMaxSpreadFilter
#define MaxSpreadPoints atlasRuntime.maxSpreadPoints
#define MaxSpreadATRRatio atlasRuntime.maxSpreadAtrRatio
#define BaseLotSize atlasRuntime.baseLotSize
#define MaxOpenOrders atlasRuntime.maxOpenOrders
#define MaxTradesPerCandle atlasRuntime.maxTradesPerCandle
#define ConsecutiveCandleThresholdBoost atlasRuntime.consecutiveCandleThresholdBoost
#define MaxConsecutiveCandleBoosts atlasRuntime.maxConsecutiveCandleBoosts
#define ZonePoints atlasRuntime.zonePoints
#define BuyDuplicateMultiplier atlasRuntime.buyDuplicateMultiplier
#define SellDuplicateMultiplier atlasRuntime.sellDuplicateMultiplier
#define MinBreakEvenProfit atlasRuntime.minBreakEvenProfit
#define ProfitThresholdMultiplier atlasRuntime.profitThresholdMultiplier
#define LossThresholdMultiplier atlasRuntime.lossThresholdMultiplier
#define MinBuySignalScore atlasRuntime.minBuySignalScore
#define MinSellSignalScore atlasRuntime.minSellSignalScore
#define EnableLimitEntry atlasRuntime.enableLimitEntry
#define LimitEntryAnchor atlasRuntime.limitEntryAnchor
#define LimitEntryATRFraction atlasRuntime.limitEntryAtrFraction
#define LimitEntryExpiryBars atlasRuntime.limitEntryExpiryBars
#define LimitEntryCancelOnFlip atlasRuntime.limitEntryCancelOnFlip
#define EnableSignalDampening atlasRuntime.enableSignalDampening
#define MaxLosingPositionsSameDir atlasRuntime.maxLosingPositionsSameDir
#define LosingPosScorePenalty atlasRuntime.losingPosScorePenalty
#define DrawdownThresholdPct atlasRuntime.drawdownThresholdPct
#define DrawdownScoreBoost atlasRuntime.drawdownScoreBoost
#define ConsecutiveLossesBeforeCooldown atlasRuntime.consecutiveLossesBeforeCooldown
#define ConsecutiveLossCooldownBars atlasRuntime.consecutiveLossCooldownBars
#define EnableLossManagement atlasRuntime.enableLossManagement
#define MaxHoldingLossPositions atlasRuntime.maxHoldingLossPositions
#define MinHealthScore atlasRuntime.minHealthScore
#define MaxAdverseATR atlasRuntime.maxAdverseAtr
#define HealthTrendWeight atlasRuntime.healthTrendWeight
#define HealthRSIWeight atlasRuntime.healthRsiWeight
#define HealthATRWeight atlasRuntime.healthAtrWeight
#define HealthSwingWeight atlasRuntime.healthSwingWeight
#define HealthRSIBuyMin atlasRuntime.healthRsiBuyMin
#define HealthRSISellMax atlasRuntime.healthRsiSellMax
#define HealthSwingLookback atlasRuntime.healthSwingLookback
#define HealthGraceBars atlasRuntime.healthGraceBars
#define EnablePartialClose atlasRuntime.enablePartialClose
#define PartialClose75Pct atlasRuntime.partialClose75Pct
#define PartialClose50Pct atlasRuntime.partialClose50Pct
#define PartialClose25Pct atlasRuntime.partialClose25Pct
#define EnableHealthSLTightening atlasRuntime.enableHealthSlTightening
#define SLTightenATRMultiplier atlasRuntime.slTightenAtrMultiplier
#define SLTightenMinHealthPct atlasRuntime.slTightenMinHealthPct
#define EnableBreakEvenOnSpread atlasRuntime.enableBreakEvenOnSpread
#define BreakEvenSpreadMultiplier atlasRuntime.breakEvenSpreadMultiplier
#define EnableVirtualSLReentry atlasRuntime.enableVirtualSlReentry
#define ReentryRespectsNewBarGate atlasRuntime.reentryRespectsNewBarGate
#define ReentryMinSignalPct atlasRuntime.reentryMinSignalPct
#define EnableProfitOffsetSL atlasRuntime.enableProfitOffsetSl
#define ConsecutiveWinsRequired atlasRuntime.consecutiveWinsRequired
#define MinOffsetProfit atlasRuntime.minOffsetProfit
#define EnableHedgeChain atlasRuntime.enableHedgeChain
#define HedgeTriggerATR atlasRuntime.hedgeTriggerAtr
#define HedgeRequireSignal atlasRuntime.hedgeRequireSignal
#define HedgeMinSignalScore atlasRuntime.hedgeMinSignalScore
#define HedgeAutoLot atlasRuntime.hedgeAutoLot
#define HedgeRecoveryATR atlasRuntime.hedgeRecoveryAtr
#define HedgeLotMultiplier atlasRuntime.hedgeLotMultiplier
#define HedgeMaxLot atlasRuntime.hedgeMaxLot
#define HedgeRecoveryPct atlasRuntime.hedgeRecoveryPct
#define HedgeRollMinProfit atlasRuntime.hedgeRollMinProfit
#define HedgeCycleLevels atlasRuntime.hedgeCycleLevels
#define EnableHedgeCycleReset atlasRuntime.enableHedgeCycleReset
#define HedgeCyclePartialPct atlasRuntime.hedgeCyclePartialPct
#define HedgeMaxCycles atlasRuntime.hedgeMaxCycles
#define HedgeMaxChainLossUSD atlasRuntime.hedgeMaxChainLossUsd
#define HedgeMaxChainLossPct atlasRuntime.hedgeMaxChainLossPct
#define HedgeClearRootSL atlasRuntime.hedgeClearRootSl
#define HedgeTrailATR atlasRuntime.hedgeTrailAtr
#define EnableDynamicLots atlasRuntime.enableDynamicLots
#define EquityDropPercent atlasRuntime.equityDropPercent
#define MaxEquityDropLotSteps atlasRuntime.maxEquityDropLotSteps
#define MinSignalStrengthForLot atlasRuntime.minSignalStrengthForLot
#define LotStepSize atlasRuntime.lotStepSize
#define MaxLotSize atlasRuntime.maxLotSize
#define EnableBasketStop atlasRuntime.enableBasketStop
#define MaxBasketLossPct atlasRuntime.maxBasketLossPct
#define MinEquityPercent atlasRuntime.minEquityPercent
#define MaxDrawdownFromPeak atlasRuntime.maxDrawdownFromPeak
#define PauseMinutes atlasRuntime.pauseMinutes
#define PauseMinutesMultiplier atlasRuntime.pauseMinutesMultiplier
#define MaxPauseMinutes atlasRuntime.maxPauseMinutes
#define MaxMinEquityTriggers atlasRuntime.maxMinEquityTriggers
#define ResetOnNewPeak atlasRuntime.resetOnNewPeak
#define TargetEquity atlasRuntime.targetEquity
#define MinimumEquity atlasRuntime.minimumEquity
#define EnableTakeProfit atlasRuntime.enableTakeProfit
#define TPInputType atlasRuntime.tpInputType
#define TPValue atlasRuntime.tpValue
#define EnableStopLoss atlasRuntime.enableStopLoss
#define SLInputType atlasRuntime.slInputType
#define SLValue atlasRuntime.slValue
#define EnableRiskReward atlasRuntime.enableRiskReward
#define RRRiskMode atlasRuntime.rrRiskMode
#define RRRiskInputType atlasRuntime.rrRiskInputType
#define RRRiskValue atlasRuntime.rrRiskValue
#define RRAtrMultiplier atlasRuntime.rrAtrMultiplier
#define RiskRewardRatio atlasRuntime.riskRewardRatio
#define EnableTrailing atlasRuntime.enableTrailing
#define TrailingEnableBreakEvenLock atlasRuntime.trailingEnableBreakEvenLock
#define TrailingSLOnProfitableOnly atlasRuntime.trailingSlOnProfitableOnly
#define EnableAdaptiveTP atlasRuntime.enableAdaptiveTp
#define EnableAdaptiveSL atlasRuntime.enableAdaptiveSl
#define TSInputType atlasRuntime.tsInputType
#define TrailingDistanceValue atlasRuntime.trailingDistanceValue
#define TrailingValueMultiplier atlasRuntime.trailingValueMultiplier
#define EnableDiscordAlerts atlasRuntime.enableDiscordAlerts
#define EnableTradingHours atlasRuntime.enableTradingHours
#define TradingStartTime atlasRuntime.tradingStartTime
#define TradingEndTime atlasRuntime.tradingEndTime
#define EnableReports atlasRuntime.enableReports
#define SendReportEveryHour atlasRuntime.sendReportEveryHour
#define EnableMarketCloseFilter atlasRuntime.enableMarketCloseFilter
#define MinutesBeforeClose atlasRuntime.minutesBeforeClose
#define EnableNewsFilter atlasRuntime.enableNewsFilter
#define NewsMinutesBefore atlasRuntime.newsMinutesBefore
#define NewsMinutesAfter atlasRuntime.newsMinutesAfter
#define EnableLeveragePause atlasRuntime.enableLeveragePause
#define EnableLogging atlasRuntime.enableLogging


void AtlasNormalizeHealthWeights()
{
    double healthWeightSum =
        atlasRuntime.healthTrendWeight +
        atlasRuntime.healthRsiWeight +
        atlasRuntime.healthAtrWeight +
        atlasRuntime.healthSwingWeight;

    if(healthWeightSum > 0.0)
    {
        normHealthTrendWeight = atlasRuntime.healthTrendWeight / healthWeightSum;
        normHealthRSIWeight   = atlasRuntime.healthRsiWeight / healthWeightSum;
        normHealthATRWeight   = atlasRuntime.healthAtrWeight / healthWeightSum;
        normHealthSwingWeight = atlasRuntime.healthSwingWeight / healthWeightSum;
    }
    else
    {
        normHealthTrendWeight = 0.25;
        normHealthRSIWeight   = 0.25;
        normHealthATRWeight   = 0.25;
        normHealthSwingWeight = 0.25;
    }

    atlasHealthWeightsDirty = false;
}

bool AtlasRebuildSignalIndicators()
{
    int newFast = iMA(_Symbol, _Period, atlasRuntime.emaFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
    int newSlow = iMA(_Symbol, _Period, atlasRuntime.emaSlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
    int newRSI  = iRSI(_Symbol, _Period, atlasRuntime.rsiPeriod, PRICE_CLOSE);
    int newATR  = iATR(_Symbol, _Period, atlasRuntime.atrPeriod);

    if(newFast == INVALID_HANDLE ||
       newSlow == INVALID_HANDLE ||
       newRSI == INVALID_HANDLE ||
       newATR == INVALID_HANDLE)
    {
        if(newFast != INVALID_HANDLE) IndicatorRelease(newFast);
        if(newSlow != INVALID_HANDLE) IndicatorRelease(newSlow);
        if(newRSI  != INVALID_HANDLE) IndicatorRelease(newRSI);
        if(newATR  != INVALID_HANDLE) IndicatorRelease(newATR);

        atlasLastGlobalBlockReason = "STRUCTURAL_REINIT_FAILED";
        Print("[ATLAS] Indicator reinitialization failed; previous handles retained.");
        return false;
    }

    if(emaFastHandle != INVALID_HANDLE) IndicatorRelease(emaFastHandle);
    if(emaSlowHandle != INVALID_HANDLE) IndicatorRelease(emaSlowHandle);
    if(rsiHandle != INVALID_HANDLE) IndicatorRelease(rsiHandle);
    if(atrSignalHandle != INVALID_HANDLE) IndicatorRelease(atrSignalHandle);

    emaFastHandle = newFast;
    emaSlowHandle = newSlow;
    rsiHandle = newRSI;
    atrSignalHandle = newATR;

    _buyStrengthValid = false;
    _sellStrengthValid = false;

    atlasStructuralConfigDirty = false;
    atlasLastGlobalBlockReason = "NONE";

    Print(
        "[ATLAS] Structural indicators rebuilt. EMAFast=",
        atlasRuntime.emaFastPeriod,
        " EMASlow=", atlasRuntime.emaSlowPeriod,
        " RSI=", atlasRuntime.rsiPeriod,
        " ATR=", atlasRuntime.atrPeriod
    );

    return true;
}

void ApplyAtlasRuntimeMaintenance()
{
    if(atlasHealthWeightsDirty)
        AtlasNormalizeHealthWeights();

    if(atlasStructuralConfigDirty &&
       emaFastHandle != INVALID_HANDLE &&
       emaSlowHandle != INVALID_HANDLE &&
       rsiHandle != INVALID_HANDLE &&
       atrSignalHandle != INVALID_HANDLE)
    {
        AtlasRebuildSignalIndicators();
    }
}


// +------------------------------------------------------------------+
// | Expert Initialization Function                                   |
// +------------------------------------------------------------------+
int OnInit()
{   
    // Load the active .set/input values into Atlas runtime state first.
    InitializeAtlasRuntime();

    EventSetTimer(1);
    ReadAtlasCommand();

    // Password protection - show dialog if password is set
    if(EA_PASSWORD != "")
    {
        passwordVerified = false;
        passwordDialogActive = true;
        
        if(!CreatePasswordDialog())
        {
            Alert("ERROR: Failed to create password dialog!");
            return(INIT_FAILED);
        }
        
        Print("🔐 Password required. Please enter password in the dialog on chart.");
        return(INIT_SUCCEEDED);
    }
    else
    {
        passwordVerified = true;
        passwordDialogActive = false;
    }
    
    // Continue with normal initialization
    return(InitializeEA());
}

// +------------------------------------------------------------------+
// | Full EA Initialization                                           |
// +------------------------------------------------------------------+
int InitializeEA()
{
    if(BaseLotSize <= 0)
    {
        Alert("ERROR: BaseLotSize must be greater than 0");
        return(INIT_PARAMETERS_INCORRECT);
    }

    if(MaxLotSize < BaseLotSize)
    {
        Alert("ERROR: MaxLotSize must be >= BaseLotSize");
        return(INIT_PARAMETERS_INCORRECT);
    }

    if(!EnableBuyOrders && !EnableSellOrders)
    {
        Alert("ERROR: Both Buy and Sell orders are disabled! EA will not trade!");
        return(INIT_PARAMETERS_INCORRECT);
    }

    string tradingHoursTestParts[];

    if(StringSplit(TradingStartTime, ':', tradingHoursTestParts) != 2)
    {
        Alert("ERROR: Invalid TradingStartTime format. Use HH:MM");
        return(INIT_PARAMETERS_INCORRECT);
    }

    if(StringSplit(TradingEndTime, ':', tradingHoursTestParts) != 2)
    {
        Alert("ERROR: Invalid TradingEndTime format. Use HH:MM");
        return(INIT_PARAMETERS_INCORRECT);
    }

    // Normalize effective Atlas runtime health weights.
    AtlasNormalizeHealthWeights();

    // Initialize Signal Indicators
    emaFastHandle = iMA(_Symbol, _Period, EMAFastPeriod, 0, MODE_EMA, PRICE_CLOSE);
    if(emaFastHandle == INVALID_HANDLE)
    {
        Print("Error creating Fast EMA handle!");
        return(INIT_FAILED);
    }
    
    emaSlowHandle = iMA(_Symbol, _Period, EMASlowPeriod, 0, MODE_EMA, PRICE_CLOSE);
    if(emaSlowHandle == INVALID_HANDLE)
    {
        Print("Error creating Slow EMA handle!");
        return(INIT_FAILED);
    }
    
    rsiHandle = iRSI(_Symbol, _Period, RSIPeriod, PRICE_CLOSE);
    if(rsiHandle == INVALID_HANDLE)
    {
        Print("Error creating RSI handle!");
        return(INIT_FAILED);
    }
    
    atrSignalHandle = iATR(_Symbol, _Period, ATRPeriod);
    if(atrSignalHandle == INVALID_HANDLE)
    {
        Print("Error creating Signal ATR handle!");
        return(INIT_FAILED);
    }

    atlasStructuralConfigDirty = false;

    initialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
    peakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    lastPeakEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    targetEquityReached = false;
    minimumEquityReached = false;
    minEquityTriggersExceeded = false;
    minEquityTriggerCount = 0;
    isPaused = false;
    pauseStartTime = 0;
    lastProcessedNewsEventID = 0;
    startTime = TimeCurrent();
    lastDailyReportTime = 0;
    lastReportEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    totalPauseCount = 0;
    totalPauseDurationMinutes = 0;
    symbolBaseCurrency = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_BASE);
    symbolQuoteCurrency = SymbolInfoString(_Symbol, SYMBOL_CURRENCY_PROFIT);
    initialLeverage = AccountInfoInteger(ACCOUNT_LEVERAGE);
    isOrderSendLocked = false;
    algoTradingStatus = TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
    
    // Initialize managed positions array
    ArrayResize(managedPositions, 0);
    managedPositionCount = 0;
    
    // Scan and register existing positions
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        if(!PositionSelectByTicket(ticket)) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
        
        ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
        double posEntryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
        
        // For existing positions, try to calculate current signal strength as baseline
        // If calculation fails or returns 0, use a default safe value (MinBuySignalScore)
        double initialScore = 0;
        
        // We can't easily get the signal at open time, so we use current as baseline
        // This effectively "resets" the signal tracking for this position
        SignalStrength strength;
        if(type == POSITION_TYPE_BUY) strength = GetSignalStrength(ORDER_TYPE_BUY);
        else strength = GetSignalStrength(ORDER_TYPE_SELL);
        
        initialScore = strength.finalScore;
        if(initialScore <= 0) initialScore = (type == POSITION_TYPE_BUY) ? atlasRuntime.minBuySignalScore : atlasRuntime.minSellSignalScore;
        
        RegisterManagedPosition(ticket, type, initialScore, posEntryPrice);

        // Update global last position tracking
        datetime posTime = (datetime)PositionGetInteger(POSITION_TIME);
        double posPrice = PositionGetDouble(POSITION_PRICE_OPEN);
        
        // Reconstruct Candle Counters for existing positions
        datetime posBarTime = (posTime / PeriodSeconds(_Period)) * PeriodSeconds(_Period);
        datetime curBarTime = iTime(_Symbol, _Period, 0);
        
        // Initialize current bar time if needed
        if(currentBarTime == 0) currentBarTime = curBarTime;
        
        if(posBarTime == currentBarTime)
        {
            if(type == POSITION_TYPE_BUY) buysOnCurrentBar++;
            else sellsOnCurrentBar++;
        }
        
        if(type == POSITION_TYPE_BUY)
        {
            if(posTime > lastBuyTime)
            {
                lastBuyTime = posTime;
                lastBuyPrice = posPrice;
            }
        }
        else if(type == POSITION_TYPE_SELL)
        {
            if(posTime > lastSellTime)
            {
                lastSellTime = posTime;
                lastSellPrice = posPrice;
            }
        }
    }
    
    Print("+-----------------------------------------+");
    Print("Nyao Scalper v43.0 Initialized Successfully");
    Print("+-----------------------------------------+");

    if(EnableDiscordAlerts) CheckDiscordAlert();
    
    return(INIT_SUCCEEDED);
}

// +------------------------------------------------------------------+
// | Expert Deinitialization Function                                 |
// +------------------------------------------------------------------+
void OnDeinit(const int reason)
{   
    // Cleanup password dialog if active
    if(passwordDialogActive)
    {
        passwordDialog.Destroy();
        passwordDialogActive = false;
    }
    
    // Cleanup Dashboard Objects
    ObjectsDeleteAll(0, "NyaoDash_");
    Comment("");
    
    // Release ATR Handle

    IndicatorRelease(emaFastHandle);
    IndicatorRelease(emaSlowHandle);
    IndicatorRelease(rsiHandle);
    IndicatorRelease(atrSignalHandle);
    EventKillTimer();
    Print("Nyao Scalper v43.0 Deinitialized");
}

void OnTimer()
{
    ReadAtlasCommand();
    ApplyAtlasRuntimeMaintenance();
    WriteAtlasStatus();
}

// +------------------------------------------------------------------+
// | Expert Tick Function                                             |
// +------------------------------------------------------------------+
void OnTick()
{
    // Block trading until password is verified
    if(!passwordVerified) return;

    // Invalidate per-tick signal cache
    _buyStrengthValid = false;
    _sellStrengthValid = false;

    // Check Algo Trading status
    CheckAlgoTradingStatus();

    // Check and update peak equity
    CheckPeakEquity();
    
    // Check if target equity reached
    CheckTargetEquity();
    
    // Check if minimum equity reached
    CheckMinTradeableEquity();

    // Check equity drawdawn
    CheckEquityDrawdawn();

    // Aggregate (basket) floating-loss protection
    CheckBasketStop();

    if(targetEquityReached || minimumEquityReached || minEquityTriggersExceeded)
    {   
        // Close all positions and completely stop the EA
        CloseAllPositions();
        DisableAlgoTrading();
        LogPrint("[STOPPED] Trading stopped.");
        UpdateDashboard();
        return;
    }

    // Check if current time is within allowed trading hours
    CheckTradingHours();

    // Check for leverage changes
    CheckLeverageChange();

    // Check for market close time
    CheckMarketClose();

    // Update Signal Globals on New Bar (for Velocity Tracking)
    datetime currBarTime = iTime(_Symbol, _Period, 0);
    if(currentBarTime != currBarTime)
    {
        // Update History Scores
        // Recalculate Score(1) which is the just-closed candle
        // We can't trust the live variable, so we re-calc
        lastBuySignalScorePrev = lastBuySignalScore;
        
        // Update Buy Stats
        SignalStrength buyStr = GetSignalStrength(ORDER_TYPE_BUY);
        lastBuySignalScore = buyStr.finalScore;
        
        // Update Sell Stats
        SignalStrength sellStr = GetSignalStrength(ORDER_TYPE_SELL);
        lastSellSignalScore = sellStr.finalScore;
        
        // Track consecutive trading candles for threshold escalation
        // If the just-closed bar had trades, increment consecutive counter
        // Otherwise reset it (the streak is broken)
        if(buysOnCurrentBar > 0)
        {
            consecutiveBuyCandles++;
            prevBarHadBuys = true;
        }
        else
        {
            consecutiveBuyCandles = 0;
            prevBarHadBuys = false;
        }
        
        if(sellsOnCurrentBar > 0)
        {
            consecutiveSellCandles++;
            prevBarHadSells = true;
        }
        else
        {
            consecutiveSellCandles = 0;
            prevBarHadSells = false;
        }
        
        // Update Bar Time
        currentBarTime = currBarTime;
        buysOnCurrentBar = 0;
        sellsOnCurrentBar = 0;
    }

    if (isOutsideTradingHours || isLeverageDiffFromInitial || isNearMarketClose)
    {   
        // Don't open new positions, but continue managing existing ones
        ManagePositions();
        // LogPrint("[PAUSED] Trading paused."); // Prevent LogPrint spam on every tick
        UpdateDashboard();
        return;
    }
    
    // Check for high-impact news events
    CheckHighImpactNews();
    
    // Check pause duration 
    if (isPaused)
    {
        datetime currentTime = TimeTradeServer();
        int elapsedSeconds = (int)(currentTime - pauseStartTime);
        int pauseDurationSeconds = currentPauseDuration * 60;
        
        if(currentPauseDuration == 0 || elapsedSeconds < pauseDurationSeconds)
        {
            // Don't open new positions, but continue managing existing ones
            ManagePositions();
            // LogPrint("[PAUSED] Paused. Time remaining: ", (pauseDurationSeconds - elapsedSeconds) / 60, " minute(s)"); // Prevent LogPrint spam on every tick
            UpdateDashboard();
            return;  // EXIT - prevent all new orders while paused
        }
        else
        {
            // Pause period ended - reset flag and resume trading
            isPaused = false;

            double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);

            LogPrint("+-----------------------------------------+");
            LogPrint("PAUSE PERIOD ENDED");
            LogPrint("Trading RESUMED after ", currentPauseDuration, " minutes");
            LogPrint("Current Equity: $", currentEquity);
            LogPrint("+-----------------------------------------+");
            
            // Send Discord alert for trading resumed
            if(EnableDiscordAlerts)
            {   
                string alertMsg = "**Instrument:** " + _Symbol + "\n";
                alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
                alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
                alertMsg += "**Pause Duration:** " + IntegerToString(currentPauseDuration) + " minutes\n";
                alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
                alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
                alertMsg += "**Action:** Trading Resumed";
                
                SendDiscordAlert("▶️ TRADING RESUMED!", alertMsg, 3066993); // Blue color
            }
        }
    }
    
    // Manage existing positions
    ManagePositions();

    // Check for trading signals
    CheckForTradingSignal();

    // Check for Trade Report
    CheckTradeReport();
    
    // Update On-Chart Dashboard
    UpdateDashboard();
}

// +------------------------------------------------------------------+
// | Chart Event Handler - Password Dialog                            |
// +------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
{
    if(passwordDialogActive)
    {
        passwordDialog.OnEvent(id, lparam, dparam, sparam);
        
        // Check for submit button click
        if(id == CHARTEVENT_OBJECT_CLICK && sparam == "PasswordSubmit")
        {
            string enteredPassword = passwordEdit.Text();
            
            if(enteredPassword == EA_PASSWORD)
            {
                // Password correct - close dialog and initialize EA
                passwordDialog.Destroy();
                passwordDialogActive = false;
                passwordVerified = true;
                
                Print("Password verified! EA is now active.");
                
                // Complete initialization
                if(InitializeEA() != INIT_SUCCEEDED)
                {
                    Alert("EA initialization failed!");
                }
            }
            else
            {
                Alert("Invalid password! Please try again.");
                passwordEdit.Text("");
            }
        }
    }
}

// +------------------------------------------------------------------+
// | Trade Transaction Handler - Primary Close Detection              |
// | Fires when a deal is added to history. We account for a fully-   |
// | closed managed position here (event-driven) instead of relying   |
// | solely on per-tick polling, which can miss closes that bunch up  |
// | on a single tick. SyncManagedPositions stays as a reconciliation |
// | fallback; ProcessClosedPosition is idempotent so there is no     |
// | double counting between the two paths.                           |
// +------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
    // Only react to a deal being added to history
    if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;

    ulong dealTicket = trans.deal;
    if(dealTicket == 0) return;
    if(!HistoryDealSelect(dealTicket)) return;

    // Only our symbol + magic
    if(HistoryDealGetString(dealTicket, DEAL_SYMBOL) != _Symbol) return;
    if(HistoryDealGetInteger(dealTicket, DEAL_MAGIC) != MagicNumber) return;

    long dealEntry = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
    ulong posID = (ulong)HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
    if(posID == 0) return;

    // NEW POSITION OPENED
    // Registers fills here so pending-limit entries get tracked. Market entries are
    // already registered inline in OpenPosition, so the index guard below skips them.
    if(dealEntry == DEAL_ENTRY_IN)
    {
        if(GetManagedPositionIndex(posID) != -1) return; // already tracked (market path)

        ENUM_POSITION_TYPE ptype;
        double entryPrice;
        string posComment = "";

        if(PositionSelectByTicket(posID))
        {
            ptype = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            posComment = PositionGetString(POSITION_COMMENT);
        }
        else
        {
            // Fallback to deal data if the position can't be selected
            ptype = (HistoryDealGetInteger(dealTicket, DEAL_TYPE) == DEAL_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
            entryPrice = HistoryDealGetDouble(dealTicket, DEAL_PRICE);
        }

        // Recover the entry-thesis score from the limit-order comment; fall back to the
        // direction's min threshold if absent (e.g. EA restarted before the fill).
        double score = ParseLimitEntryScore(posComment);
        if(score <= 0) score = (ptype == POSITION_TYPE_BUY) ? atlasRuntime.minBuySignalScore : atlasRuntime.minSellSignalScore;

        RegisterManagedPosition(posID, ptype, score, entryPrice);

        // Mirror OpenPosition's candle-counter + last-position bookkeeping for the fill bar
        datetime currBarTime = iTime(_Symbol, _Period, 0);
        if(currentBarTime != currBarTime)
        {
            currentBarTime = currBarTime;
            buysOnCurrentBar = 0;
            sellsOnCurrentBar = 0;
        }
        if(ptype == POSITION_TYPE_BUY)
        {
            buysOnCurrentBar++;
            lastBuyTime = TimeCurrent();
            lastBuyPrice = entryPrice;
        }
        else
        {
            sellsOnCurrentBar++;
            lastSellTime = TimeCurrent();
            lastSellPrice = entryPrice;
        }

        LogPrint("[LIMIT FILL] Position ", posID, " registered. Type: ",
                 ptype == POSITION_TYPE_BUY ? "BUY" : "SELL",
                 " | Entry: ", entryPrice, " | Score: ", DoubleToString(score, 1));
        return;
    }

    // POSITION CLOSED (full close accounting)
    if(dealEntry != DEAL_ENTRY_OUT && dealEntry != DEAL_ENTRY_INOUT) return;

    // Partial close — the position is still open (reduced volume); no full-close accounting
    if(PositionSelectByTicket(posID)) return;

    // Only act on positions we manage (also guards against double accounting)
    if(GetManagedPositionIndex(posID) == -1) return;

    double closedProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                        + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                        + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);

    ProcessClosedPosition(posID, closedProfit);
}

// +------------------------------------------------------------------+
// | Position Loss State - Aggregate loss metrics for a direction     |
// +------------------------------------------------------------------+
struct PositionLossState
{
    int   losingCount;                                    // Number of losing positions in this direction
    int   totalCount;                                     // Total positions in this direction
    double totalUnrealizedLoss;                           // Sum of unrealized losses (negative = loss)
    double worstLossPct;                                  // Worst single position loss as % of entry
};

// +------------------------------------------------------------------+
// | Get Open Position Loss State for a Direction                     |
// | Scans all open managed positions and returns aggregate loss info |
// +------------------------------------------------------------------+
PositionLossState GetOpenPositionLossState(ENUM_POSITION_TYPE direction)
{
    PositionLossState state;
    state.losingCount = 0;
    state.totalCount = 0;
    state.totalUnrealizedLoss = 0;
    state.worstLossPct = 0;
    
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        if(!PositionSelectByTicket(ticket)) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
        
        ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
        if(posType != direction) continue;
        
        state.totalCount++;
        double profit = PositionGetDouble(POSITION_PROFIT);
        
        if(profit < 0)
        {
            state.losingCount++;
            state.totalUnrealizedLoss += profit; // Accumulate negative value
            
            // Calculate loss as % of entry for worst-case tracking
            double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            double volume = PositionGetDouble(POSITION_VOLUME);
            double contractSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
            if(entryPrice > 0 && volume > 0 && contractSize > 0)
            {
                double lossPct = MathAbs(profit) / (entryPrice * volume * contractSize) * 100.0;
                if(lossPct > state.worstLossPct)
                    state.worstLossPct = lossPct;
            }
        }
    }
    
    return state;
}

// +------------------------------------------------------------------+
// | Get Total Floating P/L for our positions on this symbol          |
// +------------------------------------------------------------------+
double GetTotalFloatingPL()
{
    double total = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        if(!PositionSelectByTicket(ticket)) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

        total += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
    }
    return total;
}

// +------------------------------------------------------------------+
// | Floating P/L of NON hedge-chain positions only                   |
// | A hedge chain intentionally carries a transient drawdown while it |
// | recovers; including its legs here would let the basket stop close |
// | the chain prematurely. Active chain legs are bounded by their own |
// | HedgeMaxChainLossPct/USD instead. Falls back to the full total    |
// | when the hedge feature is disabled.                               |
// +------------------------------------------------------------------+
double GetBasketFloatingPL()
{
    if(!atlasRuntime.enableHedgeChain) return GetTotalFloatingPL();

    double total = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        if(!PositionSelectByTicket(ticket)) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

        int idx = GetManagedPositionIndex(ticket);
        if(idx != -1 && managedPositions[idx].chainId != 0) continue; // skip active chain legs

        total += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
    }
    return total;
}

// +------------------------------------------------------------------+
// | Basket Stop - Close all when aggregate floating loss exceeds cap |
// | Per-position management protects single trades; this is a hard   |
// | portfolio-level backstop against compounding stacked drawdown.   |
// +------------------------------------------------------------------+
void CheckBasketStop()
{
    if(!EnableBasketStop || MaxBasketLossPct <= 0) return;

    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    if(equity <= 0) return;

    // Exclude active hedge-chain legs: they are bounded by HedgeMaxChainLossPct/USD,
    // not by the basket stop (a chain's transient drawdown must not trip the basket).
    double floatingPL = GetBasketFloatingPL();
    if(floatingPL >= 0) return; // only acts on net floating loss

    double lossPct = (-floatingPL / equity) * 100.0;
    if(lossPct < MaxBasketLossPct) return;

    LogPrint("+-----------------------------------------+");
    LogPrint("BASKET STOP TRIGGERED!");
    LogPrint("Floating Loss (excl. hedge chains): $", DoubleToString(floatingPL, 2),
             " (", DoubleToString(lossPct, 2), "% of equity >= ", DoubleToString(MaxBasketLossPct, 2), "%)");
    LogPrint("Closing all non-chain positions and pausing.");
    LogPrint("+-----------------------------------------+");

    CloseAllPositions(false, true);  // skip active hedge-chain legs

    // Reuse the existing pause machinery
    if(!isPaused)
    {
        isPaused = true;
        pauseStartTime = TimeTradeServer();
        currentPauseDuration = (MaxPauseMinutes > 0) ? MathMin(PauseMinutes, MaxPauseMinutes) : PauseMinutes;
        totalPauseCount++;
        totalPauseDurationMinutes += currentPauseDuration;
    }

    if(EnableDiscordAlerts)
    {
        string alertMsg = "**Instrument:** " + _Symbol + "\n";
        alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
        alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
        alertMsg += "**Floating Loss:** $" + DoubleToString(floatingPL, 2) + " (" + DoubleToString(lossPct, 2) + "%)\n";
        alertMsg += "**Limit:** " + DoubleToString(MaxBasketLossPct, 2) + "% of equity\n";
        alertMsg += "**Pause Duration:** " + IntegerToString(currentPauseDuration) + " minutes\n";
        alertMsg += "**Action:** All Positions Closed, Trading Paused";

        SendDiscordAlert("🧺 BASKET STOP TRIGGERED", alertMsg, 15158332); // Red color
    }
}

// +------------------------------------------------------------------+
// | Check For Trading Signals                                        |
// +------------------------------------------------------------------+
void CheckForTradingSignal()
{
    // NEW-BAR ENTRY GATE
    // When enabled, evaluate/open entries only once per newly closed bar.
    if(atlasRuntime.enableNewBarEntryOnly)
    {
        datetime currBarTime = iTime(_Symbol, _Period, 0);
        if(lastEntryBarTime == currBarTime)
        {
            AtlasSetDecisionReason(POSITION_TYPE_BUY, "WAITING_FOR_NEW_BAR");
            AtlasSetDecisionReason(POSITION_TYPE_SELL, "WAITING_FOR_NEW_BAR");
            return;
        }
        lastEntryBarTime = currBarTime;
    }

    atlasBuyEntryEligible = false;
    atlasSellEntryEligible = false;
    atlasBuyBlockReason = "EVALUATING";
    atlasSellBlockReason = "EVALUATING";

    // Check Signals
    double buySignal = BuySignal();
    double sellSignal = SellSignal();

    // Process signals
    if(buySignal > sellSignal)
    {
        if(!EnableBuyOrders || !atlasBuyEnabled)
        {
            AtlasSetDecisionReason(POSITION_TYPE_BUY, "BUY_DIRECTION_DISABLED");
            LogPrint("[ATLAS] BUY entry blocked.");
            return;
        }

        if(EnableLimitEntry)
            PlaceLimitEntry(ORDER_TYPE_BUY, buySignal);
        else
            OpenPosition(ORDER_TYPE_BUY, buySignal);
    }
    else if(buySignal < sellSignal)
    {
        if(!EnableSellOrders || !atlasSellEnabled)
        {
            AtlasSetDecisionReason(POSITION_TYPE_SELL, "SELL_DIRECTION_DISABLED");
            LogPrint("[ATLAS] SELL entry blocked.");
            return;
        }

        if(EnableLimitEntry)
            PlaceLimitEntry(ORDER_TYPE_SELL, sellSignal);
        else
            OpenPosition(ORDER_TYPE_SELL, sellSignal);
    }
    else if(buySignal > 0 && sellSignal > 0)
    {
        AtlasSetDecisionReason(POSITION_TYPE_BUY, "SIGNAL_TIE");
        AtlasSetDecisionReason(POSITION_TYPE_SELL, "SIGNAL_TIE");
    }
}

// Buy Signal
double BuySignal()
{   
    double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    
    // Check strict conditions (limits & distance) first
    if(!CheckEntryConditions(POSITION_TYPE_BUY, currentPrice)) return 0;

    // Calculate smoothed signal strength (blended weighted average)
    SignalStrength strength = GetSignalStrength(ORDER_TYPE_BUY);

    double adjustedScore = strength.finalScore;
    double adjustedThreshold = atlasRuntime.minBuySignalScore;
    atlasBuyAdjustedScore = adjustedScore;
    atlasBuyEffectiveThreshold = adjustedThreshold;

    // CONSECUTIVE CANDLE THRESHOLD ESCALATION
    // When previous candles opened buy positions, raise the threshold
    // to prevent chasing moves and opening at the peak
    if(consecutiveBuyCandles > 0 && ConsecutiveCandleThresholdBoost > 0)
    {
        int boostCount = consecutiveBuyCandles;
        if(MaxConsecutiveCandleBoosts > 0 && boostCount > MaxConsecutiveCandleBoosts)
            boostCount = MaxConsecutiveCandleBoosts;
        
        double candleBoost = boostCount * ConsecutiveCandleThresholdBoost;
        adjustedThreshold += candleBoost;
        LogPrint("[CANDLE ESCALATION] Buy threshold boosted by ", DoubleToString(candleBoost, 1),
                 " (", boostCount, " consecutive trading candles). Threshold: ", 
                 DoubleToString(adjustedThreshold, 1));
    }

    // SIGNAL DAMPENING: Apply score penalty and drawdown gating
    if(EnableSignalDampening)
    {
        // A. Score Penalty: reduce score based on losing same-direction positions
        PositionLossState lossState = GetOpenPositionLossState(POSITION_TYPE_BUY);
        if(lossState.losingCount > 0)
        {
            double penalty = lossState.losingCount * LosingPosScorePenalty;
            adjustedScore -= penalty;
            LogPrint("[DAMPENED] Buy score reduced by ", DoubleToString(penalty, 1), 
                     " (", lossState.losingCount, " losing buys). Raw: ", 
                     DoubleToString(strength.finalScore, 1), " -> Adjusted: ", 
                     DoubleToString(adjustedScore, 1));
        }
        
        // B. Drawdown Gate: raise threshold when account in drawdown
        if(peakEquity > 0)
        {
            double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
            double drawdownPct = ((peakEquity - currentEquity) / peakEquity) * 100.0;
            
            if(drawdownPct >= DrawdownThresholdPct)
            {
                adjustedThreshold += DrawdownScoreBoost;
                LogPrint("[DRAWDOWN GATE] Equity drawdown ", DoubleToString(drawdownPct, 1), 
                         "% >= ", DoubleToString(DrawdownThresholdPct, 1), 
                         "%. Buy threshold raised to ", DoubleToString(adjustedThreshold, 1));
            }
        }
    }

    atlasBuyAdjustedScore = adjustedScore;
    atlasBuyEffectiveThreshold = adjustedThreshold;

    if (adjustedScore >= adjustedThreshold) 
    {   
        AtlasSetDecisionReason(POSITION_TYPE_BUY, "SIGNAL_READY", true);
        LogPrint("BUY SIGNAL RECEIVED (Score: ", DoubleToString(strength.finalScore, 1), 
                 " | Adjusted: ", DoubleToString(adjustedScore, 1), 
                 " / Threshold: ", DoubleToString(adjustedThreshold, 1), ")");
        LogPrint("Details: Body=", DoubleToString(strength.bodySignal, _Digits),
                 ", AvgBody=", DoubleToString(strength.avgBody, _Digits),
                 ", Ratio=", DoubleToString(strength.ratio, 2),
                 ", PenBody=", DoubleToString(strength.penaltyBody, 1),
                 ", PenWick=", DoubleToString(strength.penaltyWick, 1));
        LogPrint("Reasoning: ", strength.reasoning);
        LogPrint("Price: ", currentPrice);

        return adjustedScore;
    }
    
    AtlasSetDecisionReason(POSITION_TYPE_BUY, "SCORE_BELOW_THRESHOLD");
    return 0;
}

// Sell Signal
double SellSignal()
{
    double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    
    // Check strict conditions (limits & distance) first
    if(!CheckEntryConditions(POSITION_TYPE_SELL, currentPrice)) return 0;

    // Calculate smoothed signal strength (blended weighted average)
    SignalStrength strength = GetSignalStrength(ORDER_TYPE_SELL);

    double adjustedScore = strength.finalScore;
    double adjustedThreshold = atlasRuntime.minSellSignalScore;
    atlasSellAdjustedScore = adjustedScore;
    atlasSellEffectiveThreshold = adjustedThreshold;

    // CONSECUTIVE CANDLE THRESHOLD ESCALATION
    // When previous candles opened sell positions, raise the threshold
    // to prevent chasing moves and opening at the peak
    if(consecutiveSellCandles > 0 && ConsecutiveCandleThresholdBoost > 0)
    {
        int boostCount = consecutiveSellCandles;
        if(MaxConsecutiveCandleBoosts > 0 && boostCount > MaxConsecutiveCandleBoosts)
            boostCount = MaxConsecutiveCandleBoosts;
        
        double candleBoost = boostCount * ConsecutiveCandleThresholdBoost;
        adjustedThreshold += candleBoost;
        LogPrint("[CANDLE ESCALATION] Sell threshold boosted by ", DoubleToString(candleBoost, 1),
                 " (", boostCount, " consecutive trading candles). Threshold: ", 
                 DoubleToString(adjustedThreshold, 1));
    }

    // SIGNAL DAMPENING: Apply score penalty and drawdown gating
    if(EnableSignalDampening)
    {
        // A. Score Penalty: reduce score based on losing same-direction positions
        PositionLossState lossState = GetOpenPositionLossState(POSITION_TYPE_SELL);
        if(lossState.losingCount > 0)
        {
            double penalty = lossState.losingCount * LosingPosScorePenalty;
            adjustedScore -= penalty;
            LogPrint("[DAMPENED] Sell score reduced by ", DoubleToString(penalty, 1), 
                     " (", lossState.losingCount, " losing sells). Raw: ", 
                     DoubleToString(strength.finalScore, 1), " -> Adjusted: ", 
                     DoubleToString(adjustedScore, 1));
        }
        
        // B. Drawdown Gate: raise threshold when account in drawdown
        if(peakEquity > 0)
        {
            double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
            double drawdownPct = ((peakEquity - currentEquity) / peakEquity) * 100.0;
            
            if(drawdownPct >= DrawdownThresholdPct)
            {
                adjustedThreshold += DrawdownScoreBoost;
                LogPrint("[DRAWDOWN GATE] Equity drawdown ", DoubleToString(drawdownPct, 1), 
                         "% >= ", DoubleToString(DrawdownThresholdPct, 1), 
                         "%. Sell threshold raised to ", DoubleToString(adjustedThreshold, 1));
            }
        }
    }

    atlasSellAdjustedScore = adjustedScore;
    atlasSellEffectiveThreshold = adjustedThreshold;

    if (adjustedScore >= adjustedThreshold)
    {
        AtlasSetDecisionReason(POSITION_TYPE_SELL, "SIGNAL_READY", true);
        LogPrint("SELL SIGNAL RECEIVED (Score: ", DoubleToString(strength.finalScore, 1), 
                 " | Adjusted: ", DoubleToString(adjustedScore, 1), 
                 " / Threshold: ", DoubleToString(adjustedThreshold, 1), ")");
        LogPrint("Details: Body=", DoubleToString(strength.bodySignal, _Digits),
                 ", AvgBody=", DoubleToString(strength.avgBody, _Digits),
                 ", Ratio=", DoubleToString(strength.ratio, 2),
                 ", PenBody=", DoubleToString(strength.penaltyBody, 1),
                 ", PenWick=", DoubleToString(strength.penaltyWick, 1));
        LogPrint("Reasoning: ", strength.reasoning);
        LogPrint("Price: ", currentPrice);

        return adjustedScore;
    }
    
    AtlasSetDecisionReason(POSITION_TYPE_SELL, "SCORE_BELOW_THRESHOLD");
    return 0;
}

// Duplicate Buy Filter
// +------------------------------------------------------------------+
// | Unified Entry Conditions (limits, dampening, cooldown, duplicate)|
// | Direction-driven: replaces the former CheckBuy/SellConditions    |
// +------------------------------------------------------------------+
bool CheckEntryConditions(ENUM_POSITION_TYPE dir, double price)
{
    datetime currBarTime = iTime(_Symbol, _Period, 0);
    bool isBuy = (dir == POSITION_TYPE_BUY);
    string dirName = isBuy ? "Buy" : "Sell";

    int sameOnBar = isBuy ? buysOnCurrentBar : sellsOnCurrentBar;
    int oppOnBar  = isBuy ? sellsOnCurrentBar : buysOnCurrentBar;

    // Per-candle trade limit
    if(atlasRuntime.maxTradesPerCandle > 0)
    {
        int onCandle = (currentBarTime == currBarTime) ? sameOnBar : 0;
        if(onCandle >= atlasRuntime.maxTradesPerCandle)
        {
            AtlasSetDecisionReason(dir, "MAX_TRADES_PER_CANDLE");
            return false;
        }
    }

    // Prevent opposite direction trades on the same candle
    if(oppOnBar > 0)
    {
        AtlasSetDecisionReason(dir, "OPPOSITE_TRADE_ON_CANDLE");
        return false;
    }

    // SIGNAL DAMPENING: Hard block when too many losing same-dir positions are open
    if(EnableSignalDampening)
    {
        PositionLossState lossState = GetOpenPositionLossState(dir);
        if(lossState.losingCount >= MaxLosingPositionsSameDir)
        {
            AtlasSetDecisionReason(dir, "MAX_LOSING_SAME_DIRECTION");
            LogPrint("[DAMPENED] ", dirName, " BLOCKED: ", lossState.losingCount,
                     " losing ", dirName, "s >= max ", MaxLosingPositionsSameDir);
            return false;
        }
    }

    // SIGNAL DAMPENING: Cooldown after consecutive losses
    if(EnableSignalDampening && cooldownUntilBarTime > 0)
    {
        if(currBarTime < cooldownUntilBarTime)
        {
            AtlasSetDecisionReason(dir, "CONSECUTIVE_LOSS_COOLDOWN");
            LogPrint("[COOLDOWN] ", dirName, " BLOCKED: cooldown active until ",
                     TimeToString(cooldownUntilBarTime));
            return false;
        }
        else
        {
            cooldownUntilBarTime = 0;
        }
    }

    // Check minimum distance from last same-dir entry (duplicate signal filter)
    ulong lastTicket  = GetLastPositionTicket(dir);
    datetime lastTime = isBuy ? lastBuyTime : lastSellTime;
    double lastPrice  = isBuy ? lastBuyPrice : lastSellPrice;
    double dupMult    = isBuy ? BuyDuplicateMultiplier : SellDuplicateMultiplier;

    if(lastTime > 0 && lastTicket > 0)
    {
        double minDistance = ZonePoints * _Point * dupMult;
        double distance = MathAbs(price - lastPrice);

        if(distance < minDistance)
        {
            AtlasSetDecisionReason(dir, "DUPLICATE_DISTANCE");
            return false;
        }
    }

    AtlasSetDecisionReason(dir, "ENTRY_CONDITIONS_OK");
    return true;
}
// +------------------------------------------------------------------+

// +------------------------------------------------------------------+
// | Manage Positions                                                 |
// +------------------------------------------------------------------+
void ManagePositions()
{   
    // Sync managed positions with broker (remove closed ones)
    SyncManagedPositions();

    // Hedge chain recovery: manage existing chains (resolve / stop / extend) and start
    // new chains for losing positions. Runs before trailing/loss management so chain
    // legs are correctly frozen/skipped by those routines.
    ManageHedgeChains();

    // Manage trailing stops for all positions
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        
        if(!PositionSelectByTicket(ticket)) continue;
        
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

        // Manage Trailing TP & SL for all positions
        ManageTrailingTPSL(ticket);
    }

    // Manage losing positions
    ManageLosingPositions();

    // Expire / cancel stale pending limit entries (no-op when EnableLimitEntry is off)
    ManagePendingOrders();
}

// +------------------------------------------------------------------+
// | Compute Raw Score - Internal Helper                              |
// | Computes the raw signal score for a given candle index           |
// | signalIndex: 0 = current forming candle, 1+ = closed candles     |
// +------------------------------------------------------------------+
double ComputeRawScore(ENUM_ORDER_TYPE orderType, int signalIndex)
{
    SignalStrength dummy;
    return ComputeRawScore(orderType, signalIndex, dummy, false);
}

double ComputeRawScore(ENUM_ORDER_TYPE orderType, int signalIndex, SignalStrength &components, bool fillComponents)
{
    bool isBuy = (orderType == ORDER_TYPE_BUY);
    bool isSell = (orderType == ORDER_TYPE_SELL);

    double bufEMA_Fast[], bufEMA_Slow[], bufRSI[], bufATR[];
    ArraySetAsSeries(bufEMA_Fast, true);
    ArraySetAsSeries(bufEMA_Slow, true);
    ArraySetAsSeries(bufRSI, true);
    ArraySetAsSeries(bufATR, true);

    // Copy minimal buffers
    int needed = MathMax(ImpulseLookback, MathMax(DirectionalBodyLookback, ATRAvgLookback)) + 5;

    // Fast EMA needs enough history for a multi-bar slope (SlopeLookback bars back)
    int slopeBars = (SlopeLookback < 1) ? 1 : SlopeLookback;
    int emaFastCopy = MathMax(3, slopeBars + 1);

    if(CopyBuffer(emaFastHandle, 0, signalIndex, emaFastCopy, bufEMA_Fast) < emaFastCopy) return 0;
    if(CopyBuffer(emaSlowHandle, 0, signalIndex, 3, bufEMA_Slow) < 3) return 0;
    if(CopyBuffer(rsiHandle, 0, signalIndex, 3, bufRSI) < 3) return 0;
    if(CopyBuffer(atrSignalHandle, 0, signalIndex, needed, bufATR) < needed) return 0;

    // Fetch Price Data
    MqlRates rates[];
    ArraySetAsSeries(rates, true);
    if(CopyRates(_Symbol, _Period, signalIndex, needed, rates) < needed) return 0;

    // 1. TREND SCORE (Max 3)
    double emaFast = bufEMA_Fast[0];
    double emaSlow = bufEMA_Slow[0];
    // Multi-bar slope: compare current Fast EMA against its value SlopeLookback bars ago
    // (less whipsaw than a single-bar slope on noisy M1 data)
    double emaFastPrev = bufEMA_Fast[slopeBars];
    double trendScore = 0;

    bool trendAligned = false;
    if (isBuy) trendAligned = (emaFast > emaSlow);
    else trendAligned = (emaFast < emaSlow);
    if (trendAligned) trendScore += TrendWeight;

    bool slopeAligned = false;
    if (isBuy) slopeAligned = (emaFast > emaFastPrev);
    else slopeAligned = (emaFast < emaFastPrev);
    if (slopeAligned) trendScore += SlopeWeight;
    if(trendScore > 3.0) trendScore = 3.0;

    // 2. MOMENTUM SCORE (Max 3) + IMPULSE
    double currentBody = MathAbs(rates[0].close - rates[0].open);
    double sumBody = 0;
    int validCandles = 0;
    for(int i=1; i<=DirectionalBodyLookback && i<needed; i++)
    {
        sumBody += MathAbs(rates[i].close - rates[i].open);
        validCandles++;
    }
    double avgRecentBody = (validCandles > 0) ? sumBody / validCandles : currentBody;

    double rsi = bufRSI[0];
    double baseMomentum = 0;

    if (isBuy)
    {
        if (rsi > 50 && rsi < RSIOverbought) baseMomentum += MomentumBaseWeight;
        if (rsi > RSIMomentumBuy) baseMomentum += MomentumTriggerWeight;
        if (currentBody > avgRecentBody) baseMomentum += BodyMomentumWeight;
    }
    else
    {
        if (rsi < 50 && rsi > RSIOversold) baseMomentum += MomentumBaseWeight;
        if (rsi < RSIMomentumSell) baseMomentum += MomentumTriggerWeight;
        if (currentBody > avgRecentBody) baseMomentum += BodyMomentumWeight;
    }

    double momentumScore = baseMomentum;

    // IMPULSE DETECTION
    double bodyAccel = 0;
    if (avgRecentBody > 0) bodyAccel = currentBody / avgRecentBody;
    if (bodyAccel > 3.0) bodyAccel = 3.0;

    double currentRange = rates[0].high - rates[0].low;
    double sumRange = 0;
    for(int i=1; i<=DirectionalBodyLookback && i<needed; i++)
    {
        sumRange += (rates[i].high - rates[i].low);
    }
    double avgRecentRange = (validCandles > 0) ? sumRange / validCandles : currentRange;

    double rangeAccel = 0;
    if (avgRecentRange > 0) rangeAccel = currentRange / avgRecentRange;
    if (rangeAccel > 3.0) rangeAccel = 3.0;

    int sameDirCount = 0;
    for(int i=0; i<ImpulseLookback && i<needed; i++)
    {
        bool candleBullish = (rates[i].close > rates[i].open);
        bool candleBearish = (rates[i].close < rates[i].open);

        if (isBuy && candleBullish) sameDirCount++;
        else if (isSell && candleBearish) sameDirCount++;
        else break;
    }
    double continuityScore = (double)sameDirCount / ImpulseLookback;
    if(continuityScore > 1.0) continuityScore = 1.0;

    double rawImpulse = (0.5 * bodyAccel + 0.3 * rangeAccel + 0.2 * continuityScore) / 2.0;
    if (rawImpulse > 1.0) rawImpulse = 1.0;
    if (rawImpulse < 0.0) rawImpulse = 0.0;

    momentumScore = momentumScore * (1.0 + ImpulseBoostWeight * rawImpulse);
    if (momentumScore > 3.0) momentumScore = 3.0;

    // 3. CHOP SCORE (Max 2)
    double currentATR = bufATR[0];
    double avgATR = 0;
    if (needed >= ATRAvgLookback) {
         double sumATR = 0;
         for(int i=0; i<ATRAvgLookback && i<needed; i++) sumATR += bufATR[i];
         avgATR = sumATR / ATRAvgLookback;
    } else {
         avgATR = currentATR;
    }

    double volRatio = 0;
    if(avgATR > 0) volRatio = currentATR / avgATR;

    // DEAD-MARKET FILTER: when ATR has collapsed relative to its average the
    // market is too quiet to scalp profitably (costs dominate). Block the signal.
    // Guard volRatio > 0 so we don't block when ATR data is unavailable.
    if(atlasRuntime.minVolRatioToTrade > 0 && volRatio > 0 && volRatio < atlasRuntime.minVolRatioToTrade)
        return 0;

    double chopScore = 0;
    if (volRatio > 1.0) chopScore = ChopScoreHigh;
    else if (volRatio > 0.8) chopScore = ChopScoreMed;
    else chopScore = ChopScoreLow;
    if (chopScore > 2.0) chopScore = 2.0;

    // 4. PEAK & VOLATILITY SCORES (Max 1 each)
    double volatilityScore = (volRatio > 1.2) ? VolatilityScoreHigh : VolatilityScoreLow;

    bool breakout = false;
    double localExtreme = isBuy ? rates[1].high : rates[1].low;
    for(int i=2; i<=5; i++)
    {
         if(isBuy) localExtreme = MathMax(localExtreme, rates[i].high);
         else localExtreme = MathMin(localExtreme, rates[i].low);
    }

    double peakScore = 0;
    if(isBuy && rates[0].close > localExtreme) breakout = true;
    if(isSell && rates[0].close < localExtreme) breakout = true;
    if(breakout) peakScore = PeakScoreWeight;

    // 5. WICK / REJECTION PENALTY
    double maxOpenClose = MathMax(rates[0].open, rates[0].close);
    double minOpenClose = MathMin(rates[0].open, rates[0].close);
    double upperWick = rates[0].high - maxOpenClose;
    double lowerWick = minOpenClose - rates[0].low;

    double safeBody = MathMax(currentBody, avgRecentBody * MinBodyRatio);
    double penaltyWick = 0;
    double rejection = 0;

    if (safeBody > 0)
    {
        if (isBuy) rejection = upperWick / safeBody;
        else rejection = lowerWick / safeBody;
        penaltyWick = rejection * WickRejectionWeight;
    }

    // FINAL SCORE AGGREGATION
    double rawScore = trendScore + momentumScore + chopScore + peakScore + volatilityScore;
    rawScore -= penaltyWick;

    if (rawScore < 0) rawScore = 0;
    if (rawScore > 10.0) rawScore = 10.0;

    // Fill component details for dashboard reporting
    if(fillComponents)
    {
        components.trendScore = trendScore;
        components.momentumScore = momentumScore;
        components.chopScore = chopScore;
        components.peakScore = peakScore;
        components.volatilityScore = volatilityScore;
        components.impulseStrength = rawImpulse;
        components.avgBody = avgRecentBody;
        components.bodySignal = currentBody;
        components.upperWick = upperWick;
        components.lowerWick = lowerWick;
        components.rejection = rejection;
        components.penaltyWick = penaltyWick;
    }

    return rawScore;
}

// +------------------------------------------------------------------+
// | Signal Strength Analysis - Blended Weighted Average              |
// | Combines weighted avg of N closed candles + dampened current     |
// | candle for smooth yet responsive signal scoring                  |
// +------------------------------------------------------------------+
SignalStrength GetSignalStrength(ENUM_ORDER_TYPE orderType)
{
    // Return cached result if already computed this tick
    if(orderType == ORDER_TYPE_BUY && _buyStrengthValid)
        return _cachedBuyStrength;
    if(orderType == ORDER_TYPE_SELL && _sellStrengthValid)
        return _cachedSellStrength;

    SignalStrength strength;
    strength.finalScore = 0;
    strength.trendScore = 0;
    strength.momentumScore = 0;
    strength.chopScore = 0;
    strength.peakScore = 0;
    strength.volatilityScore = 0;
    strength.impulseStrength = 0;
    strength.velocity = 0;
    strength.normalizedVelocity = 0;
    strength.avgBody = 0;
    strength.bodySignal = 0;
    strength.ratio = 0;
    strength.upperWick = 0;
    strength.lowerWick = 0;
    strength.rejection = 0;
    strength.penaltyBody = 0;
    strength.penaltyWick = 0;
    strength.reasoning = "";
    
    bool isBuy = (orderType == ORDER_TYPE_BUY);
    
    // Clamp smoothing parameters to safe ranges
    int N = SignalSmoothingCandles;
    if(N < 1) N = 1;
    if(N > 10) N = 10;
    double blend = CurrentCandleBlend;
    if(blend < 0.0) blend = 0.0;
    if(blend > 1.0) blend = 1.0;
    
    // Step 1: Weighted average of last N closed candles (the "base")
    // Weights: candle[1] = N, candle[2] = N-1, ..., candle[N] = 1
    double weightedSum = 0;
    double weightTotal = 0;
    
    for(int i = 1; i <= N; i++)
    {
        // Fill component details on candle[1] for dashboard reporting
        double score_i = (i == 1)
            ? ComputeRawScore(orderType, i, strength, true)
            : ComputeRawScore(orderType, i);
        double weight = (double)(N - i + 1); // Linear decay
        weightedSum += score_i * weight;
        weightTotal += weight;
    }

    double baseScore = (weightTotal > 0) ? weightedSum / weightTotal : 0;

    // Step 2: Compute current candle score (dampened contribution)
    double currentScore = ComputeRawScore(orderType, 0);
    
    // Step 3: Blend
    double finalScore = baseScore * (1.0 - blend) + currentScore * blend;
    
    // Clamp
    if(finalScore < 0) finalScore = 0;
    if(finalScore > 10.0) finalScore = 10.0;
    
    strength.finalScore = finalScore;
    
    // VELOCITY TRACKING
    // Use smoothed scores for velocity (inherently smoother)
    double prevScore = 0;
    if (isBuy)
    {
        prevScore = lastBuySignalScorePrev;
    }
    else
    {
        prevScore = lastSellSignalScorePrev;
    }
    
    double velocity = strength.finalScore - prevScore;
    strength.velocity = velocity;
    
    // Normalized Velocity
    strength.normalizedVelocity = (velocity + VelocityWindow) / (2.0 * VelocityWindow);
    if(strength.normalizedVelocity < 0) strength.normalizedVelocity = 0;
    if(strength.normalizedVelocity > 1.0) strength.normalizedVelocity = 1.0;
    
    // Update Globals for Position Sizing (Latest Call Wins)
    if(isBuy) {
        lastBuyVelocity = strength.velocity;
        lastBuyNormalizedVelocity = strength.normalizedVelocity;
    } else {
        lastSellVelocity = strength.velocity;
        lastSellNormalizedVelocity = strength.normalizedVelocity;
    }
    
    // Debug Construction
    strength.reasoning = StringFormat("T:%.1f M:%.1f(Imp:%.2f) C:%.1f P:%.1f V:%.1f | Vel:%.2f [Smooth:%d Blend:%.0f%%]",
        strength.trendScore, strength.momentumScore, strength.impulseStrength,
        strength.chopScore, strength.peakScore, strength.volatilityScore, strength.normalizedVelocity,
        N, blend * 100);

    // Cache result for this tick
    if(orderType == ORDER_TYPE_BUY) { _cachedBuyStrength = strength; _buyStrengthValid = true; }
    else { _cachedSellStrength = strength; _sellStrengthValid = true; }

    return strength;
}

// +------------------------------------------------------------------+
// | Evaluate Position Health - Measurement-Based Revalidation        |
// | Checks if the trade thesis is still valid                        |
// | Uses smoothed inputs + graduated trend with slope awareness      |
// +------------------------------------------------------------------+
PositionHealth EvaluatePositionHealth(
    ENUM_POSITION_TYPE posType, 
    double entryPrice,
    datetime posOpenTime,
    double emaFast, 
    double emaSlow, 
    double emaFastPrev,
    double rsi, 
    double currentATR,
    const MqlRates &rates[],
    int ratesCount)
{
    PositionHealth health;
    health.healthScore = 0;
    health.trendValid = false;
    health.momentumValid = false;
    health.adverseATR = 0;
    health.swingValid = true;
    health.inGracePeriod = false;
    health.reason = "";
    
    bool isBuy = (posType == POSITION_TYPE_BUY);
    
    // GRACE PERIOD CHECK
    // Skip health evaluation for newly opened positions
    if(HealthGraceBars > 0 && posOpenTime > 0)
    {
        int barsElapsed = iBarShift(_Symbol, _Period, posOpenTime, false);
        if(barsElapsed < HealthGraceBars)
        {
            health.healthScore = 1.0;
            health.trendValid = true;
            health.momentumValid = true;
            health.swingValid = true;
            health.inGracePeriod = true;
            health.reason = StringFormat("Grace period (%d/%d bars). ", barsElapsed, HealthGraceBars);
            return health;
        }
    }
    
    // 1. TREND ALIGNMENT (Graduated: separation + slope awareness)
    // Factors:
    //   a. EMA crossed correctly (base requirement)
    //   b. EMA separation relative to ATR (how strongly crossed)
    //   c. EMA slope direction (is fast EMA still moving favorably?)
    double trendScore = 0;
    if(isBuy)
        health.trendValid = (emaFast > emaSlow);
    else
        health.trendValid = (emaFast < emaSlow);
    
    if(health.trendValid)
    {
        // a. EMA separation: how far apart the EMAs are relative to ATR
        //    Full score at 0.5 ATR separation, scales linearly below that
        double emaSeparation = MathAbs(emaFast - emaSlow);
        double separationScore = 1.0;
        if(currentATR > 0)
        {
            separationScore = MathMin(1.0, emaSeparation / (currentATR * 0.5));
        }
        
        // b. EMA slope: is the fast EMA still moving in the favorable direction?
        //    Full score if slope is favorable, 0.7 penalty if slope is flattening/reversing
        double slopeFactor = 1.0;
        if(isBuy)
        {
            if(emaFast <= emaFastPrev) slopeFactor = 0.7; // Slope flattening or reversing
        }
        else
        {
            if(emaFast >= emaFastPrev) slopeFactor = 0.7; // Slope flattening or reversing
        }
        
        trendScore = separationScore * slopeFactor;
        
        if(slopeFactor < 1.0)
            health.reason += StringFormat("EMA slope weakening (sep=%.1f%% ATR). ", 
                currentATR > 0 ? emaSeparation / currentATR * 100 : 0);
    }
    else
    {
        trendScore = 0;
        health.reason += "Trend crossed against position. ";
    }
    
    // 2. RSI ZONE (Graduated: linear ramp from 0 to 1)
    // Uses configurable thresholds instead of hardcoded 45/55
    double rsiScore = 0;
    if(isBuy)
    {
        // Buy: RSI should be above HealthRSIBuyMin
        // Score ramps from 0 at HealthRSIBuyMin-15 to 1.0 at HealthRSIBuyMin
        double rsiFloor = HealthRSIBuyMin - 15.0;
        if(rsi >= HealthRSIBuyMin)
        {
            rsiScore = 1.0;
            health.momentumValid = true;
        }
        else if(rsi > rsiFloor)
        {
            rsiScore = (rsi - rsiFloor) / (HealthRSIBuyMin - rsiFloor);
            health.momentumValid = false;
            health.reason += StringFormat("RSI weakening (RSI=%.1f, min=%.1f). ", rsi, HealthRSIBuyMin);
        }
        else
        {
            rsiScore = 0;
            health.momentumValid = false;
            health.reason += StringFormat("RSI regime shift (RSI=%.1f, min=%.1f). ", rsi, HealthRSIBuyMin);
        }
    }
    else
    {
        // Sell: RSI should be below HealthRSISellMax
        // Score ramps from 0 at HealthRSISellMax+15 to 1.0 at HealthRSISellMax
        double rsiCeiling = HealthRSISellMax + 15.0;
        if(rsi <= HealthRSISellMax)
        {
            rsiScore = 1.0;
            health.momentumValid = true;
        }
        else if(rsi < rsiCeiling)
        {
            rsiScore = (rsiCeiling - rsi) / (rsiCeiling - HealthRSISellMax);
            health.momentumValid = false;
            health.reason += StringFormat("RSI weakening (RSI=%.1f, max=%.1f). ", rsi, HealthRSISellMax);
        }
        else
        {
            rsiScore = 0;
            health.momentumValid = false;
            health.reason += StringFormat("RSI regime shift (RSI=%.1f, max=%.1f). ", rsi, HealthRSISellMax);
        }
    }
    
    // 3. ADVERSE EXCURSION / ATR (Graduated: smooth falloff based on distance)
    double currentPrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double adverseMove = 0;
    
    if(isBuy)
        adverseMove = entryPrice - currentPrice;  // Positive = losing
    else
        adverseMove = currentPrice - entryPrice;  // Positive = losing
    
    double atrScore = 1.0;  // Default: fully healthy (not adverse)
    if(currentATR > 0 && adverseMove > 0)
    {
        health.adverseATR = adverseMove / currentATR;
        // Graduated: score drops linearly from 1.0 at 0 ATR to 0.0 at MaxAdverseATR
        atrScore = MathMax(0.0, 1.0 - (health.adverseATR / MaxAdverseATR));
        
        if(health.adverseATR > MaxAdverseATR)
            health.reason += StringFormat("Adverse excursion %.1f ATR > Max %.1f ATR. ", health.adverseATR, MaxAdverseATR);
        else if(atrScore < 0.5)
            health.reason += StringFormat("Adverse excursion %.1f ATR (score=%.2f). ", health.adverseATR, atrScore);
    }
    
    // 4. SWING LEVEL (Graduated: binary — structure IS or ISN'T broken)
    // Uses configurable lookback, excludes 2 most recent bars to avoid noise
    double swingScore = 1.0;
    int swingLookback = MathMax(5, HealthSwingLookback);  // Minimum 5 bars
    
    if(ratesCount >= swingLookback)
    {
        // Start from bar index 2 (skip 2 most recent to avoid noise)
        int startBar = MathMin(2, ratesCount - 1);
        
        if(isBuy)
        {
            // Find recent swing low — if price broke below it, structure is broken
            double swingLow = rates[startBar].low;
            for(int j = startBar + 1; j < swingLookback && j < ratesCount; j++)
                swingLow = MathMin(swingLow, rates[j].low);
            
            if(currentPrice < swingLow)
            {
                swingScore = 0;
                health.swingValid = false;
                health.reason += StringFormat("Price %.5f broke swing low %.5f (%d bars). ", currentPrice, swingLow, swingLookback);
            }
        }
        else
        {
            // Find recent swing high — if price broke above it, structure is broken
            double swingHigh = rates[startBar].high;
            for(int j = startBar + 1; j < swingLookback && j < ratesCount; j++)
                swingHigh = MathMax(swingHigh, rates[j].high);
            
            if(currentPrice > swingHigh)
            {
                swingScore = 0;
                health.swingValid = false;
                health.reason += StringFormat("Price %.5f broke swing high %.5f (%d bars). ", currentPrice, swingHigh, swingLookback);
            }
        }
    }
    
    // AGGREGATE HEALTH SCORE (Graduated, using normalized weights)
    health.healthScore = (trendScore  * normHealthTrendWeight)
                       + (rsiScore    * normHealthRSIWeight)
                       + (atrScore    * normHealthATRWeight)
                       + (swingScore  * normHealthSwingWeight);
    
    if(health.reason == "")  health.reason = "All health checks passed.";
    
    return health;
}

// +------------------------------------------------------------------+
// | Manage Losing Positions                                          |
// | Scaled Partial Close, Dynamic SL Tightening, Break-Even Lock,    |
// | Virtual SL + Re-entry                                            |
// +------------------------------------------------------------------+
void ManageLosingPositions()
{   
    if(!EnableLossManagement) return;
    
    // Cache indicator data once before the position loop
    double bufEMA_Fast[], bufEMA_Slow[], bufRSI[], bufATR[];
    ArraySetAsSeries(bufEMA_Fast, true);
    ArraySetAsSeries(bufEMA_Slow, true);
    ArraySetAsSeries(bufRSI, true);
    ArraySetAsSeries(bufATR, true);
    
    // Fetch 3 values: [0]=current, [1]=closed, [2]=prev closed (for slope)
    if(CopyBuffer(emaFastHandle, 0, 0, 3, bufEMA_Fast) < 3) return;
    if(CopyBuffer(emaSlowHandle, 0, 0, 3, bufEMA_Slow) < 3) return;
    if(CopyBuffer(rsiHandle, 0, 0, 3, bufRSI) < 3) return;
    if(CopyBuffer(atrSignalHandle, 0, 0, 3, bufATR) < 3) return;
    
    // Blend closed candle + current candle indicators (consistent with signal smoothing)
    // ATR stays on closed candle for stable volatility baseline
    double blend = CurrentCandleBlend;
    if(blend < 0.0) blend = 0.0;
    if(blend > 1.0) blend = 1.0;
    
    double emaFast = bufEMA_Fast[1] * (1.0 - blend) + bufEMA_Fast[0] * blend;
    double emaSlow = bufEMA_Slow[1] * (1.0 - blend) + bufEMA_Slow[0] * blend;
    double emaFastPrev = bufEMA_Fast[2]; // Previous closed candle (for slope detection)
    double rsi = bufRSI[1] * (1.0 - blend) + bufRSI[0] * blend;
    double currentATR = bufATR[1]; // ATR on closed candle (stable baseline)
    
    // Cache rates for swing level check
    int swingBars = MathMax(5, HealthSwingLookback);
    MqlRates rates[];
    ArraySetAsSeries(rates, true);
    int ratesCopied = CopyRates(_Symbol, _Period, 1, swingBars, rates);
    
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        if(!PositionSelectByTicket(ticket)) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
        
        ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
        datetime posOpenTime = (datetime)PositionGetInteger(POSITION_TIME);
        double volume = PositionGetDouble(POSITION_VOLUME);
        double profit = PositionGetDouble(POSITION_PROFIT);
        double currentSL = PositionGetDouble(POSITION_SL);
        double currentTP = PositionGetDouble(POSITION_TP);
        
        // Get managed position data
        int posIndex = GetManagedPositionIndex(ticket);
        if(posIndex == -1)
        {
            double posEntryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
            RegisterManagedPosition(ticket, posType, 0, posEntryPrice);
            continue;
        }

        // HEDGE CHAIN: chain logic exclusively manages legs of an active chain.
        // Skip the standard loss management (health close, partial, SL tighten, re-entry).
        if(atlasRuntime.enableHedgeChain && managedPositions[posIndex].chainId != 0)
            continue;

        double entryPrice = managedPositions[posIndex].entryPrice;
        double initialScore = managedPositions[posIndex].signalScore;
        
        // Evaluate position health
        PositionHealth health = EvaluatePositionHealth(posType, entryPrice, posOpenTime, 
                                                       emaFast, emaSlow, emaFastPrev, rsi, currentATR, 
                                                       rates, ratesCopied);
        
        // Skip all management during grace period
        if(health.inGracePeriod) continue;
        
        // 1. BREAK-EVEN LOCK (when profit exceeds spread cost)
        if(EnableBreakEvenOnSpread && !managedPositions[posIndex].breakEvenLocked)
        {
            double spreadPoints = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) * _Point;
            double spreadCost = spreadPoints * volume * SymbolInfoDouble(_Symbol, SYMBOL_TRADE_CONTRACT_SIZE);
            double breakEvenTrigger = spreadCost * BreakEvenSpreadMultiplier;
            
            if(profit > breakEvenTrigger)
            {
                // Calculate break-even SL at entry price
                double newBESL = NormalizeDouble(entryPrice, _Digits);
                
                // Validate: SL must be on the correct side
                long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
                double minDist = stopLevel * _Point;
                bool canLockBE = false;
                
                if(posType == POSITION_TYPE_BUY)
                {
                    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                    canLockBE = (newBESL < bid - minDist) && (currentSL == 0 || newBESL > currentSL);
                }
                else
                {
                    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                    canLockBE = (newBESL > ask + minDist) && (currentSL == 0 || newBESL < currentSL);
                }
                
                if(canLockBE)
                {
                    if(ModifyPosition(ticket, newBESL, currentTP))
                    {
                        managedPositions[posIndex].breakEvenLocked = true;
                        
                        LogPrint("+-----------------------------------------+");
                        LogPrint("[BREAK-EVEN LOCKED] Ticket: ", ticket);
                        LogPrint("Profit: $", DoubleToString(profit, 2), " > Trigger: $", DoubleToString(breakEvenTrigger, 2));
                        LogPrint("SL moved to entry: ", newBESL);
                        LogPrint("+-----------------------------------------+");
                    }
                }
            }
        }
        
        // 2. SCALED PARTIAL CLOSE (signal decay based)
        if(EnablePartialClose && initialScore > 0 && managedPositions[posIndex].partialCloseLevel < 3)
        {
            // Get current signal strength for position's direction
            ENUM_ORDER_TYPE orderType = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
            SignalStrength currentStrength = GetSignalStrength(orderType);
            double currentScore = currentStrength.finalScore;
            double signalRatio = currentScore / initialScore;
            
            // Re-read position volume (may have changed from previous partial close)
            if(!PositionSelectByTicket(ticket)) continue;
            volume = PositionGetDouble(POSITION_VOLUME);
            
            double minVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
            double stepVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
            
            // Level 1: Signal drops to 75% -> Close 25%
            if(managedPositions[posIndex].partialCloseLevel == 0 && signalRatio <= 0.75)
            {
                double closeVol = NormalizeVolume(volume * PartialClose75Pct);
                double remaining = volume - closeVol;
                
                if(closeVol >= minVol && remaining >= minVol)
                {
                    if(PartialClosePosition(ticket, closeVol))
                    {
                        managedPositions[posIndex].partialCloseLevel = 1;
                        LogPrint("+-----------------------------------------+");
                        LogPrint("[PARTIAL CLOSE L1] Ticket: ", ticket);
                        LogPrint("Signal: ", DoubleToString(currentScore, 1), " / ", DoubleToString(initialScore, 1), " (", DoubleToString(signalRatio * 100, 0), "%)");
                        LogPrint("Closed: ", closeVol, " lots | Remaining: ", remaining, " lots");
                        LogPrint("+-----------------------------------------+");
                    }
                }
            }
            // Level 2: Signal drops to 50% -> Close 50%
            else if(managedPositions[posIndex].partialCloseLevel == 1 && signalRatio <= 0.50)
            {
                // Re-read volume after potential L1 close
                if(!PositionSelectByTicket(ticket)) continue;
                volume = PositionGetDouble(POSITION_VOLUME);
                
                double closeVol = NormalizeVolume(volume * PartialClose50Pct);
                double remaining = volume - closeVol;
                
                if(closeVol >= minVol && remaining >= minVol)
                {
                    if(PartialClosePosition(ticket, closeVol))
                    {
                        managedPositions[posIndex].partialCloseLevel = 2;
                        LogPrint("+-----------------------------------------+");
                        LogPrint("[PARTIAL CLOSE L2] Ticket: ", ticket);
                        LogPrint("Signal: ", DoubleToString(currentScore, 1), " / ", 
                                 DoubleToString(initialScore, 1), " (", DoubleToString(signalRatio * 100, 0), "%)");
                        LogPrint("Closed: ", closeVol, " lots | Remaining: ", remaining, " lots");
                        LogPrint("+-----------------------------------------+");
                    }
                }
            }
            // Level 3: Signal drops to 25% -> Close remaining
            else if(managedPositions[posIndex].partialCloseLevel == 2 && signalRatio <= 0.25)
            {
                LogPrint("+-----------------------------------------+");
                LogPrint("[PARTIAL CLOSE L3 - FULL EXIT] Ticket: ", ticket);
                LogPrint("Signal: ", DoubleToString(currentScore, 1), " / ", 
                         DoubleToString(initialScore, 1), " (", DoubleToString(signalRatio * 100, 0), "%)");
                LogPrint("+-----------------------------------------+");
                
                managedPositions[posIndex].partialCloseLevel = 3;
                ClosePosition(ticket);
                
                // Virtual SL Re-entry after L3 full close
                if(atlasRuntime.enableVirtualSlReentry)
                {
                    TryVirtualSLReentry(posType, initialScore);
                }
                continue; // Position is fully closed
            }
        }
        
        // 3. DYNAMIC SL TIGHTENING (health-based)
        if(EnableHealthSLTightening && health.healthScore < SLTightenMinHealthPct && currentATR > 0)
        {
            // Calculate tightened SL: distance shrinks proportionally with health
            // healthRatio = health / startThreshold (1.0 at threshold, 0.0 at dead)
            double healthRatio = health.healthScore / SLTightenMinHealthPct;
            if(healthRatio < 0.1) healthRatio = 0.1; // Prevent SL at entry (would be break-even)
            
            double slDistance = currentATR * SLTightenATRMultiplier * healthRatio;
            double newTightenedSL = 0;
            
            // Re-read position to ensure consistency
            if(!PositionSelectByTicket(ticket)) continue;
            currentSL = PositionGetDouble(POSITION_SL);
            currentTP = PositionGetDouble(POSITION_TP);
            
            long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
            double minDist = stopLevel * _Point;
            
            if(posType == POSITION_TYPE_BUY)
            {
                double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                newTightenedSL = NormalizeDouble(bid - slDistance, _Digits);
                
                // Respect break-even lock
                if(managedPositions[posIndex].breakEvenLocked && newTightenedSL < entryPrice)
                    newTightenedSL = NormalizeDouble(entryPrice, _Digits);
                
                // Only move SL UP (more protective)
                if(currentSL > 0 && newTightenedSL <= currentSL) continue;
                
                // Respect minimum stop distance
                if(newTightenedSL >= bid - minDist) continue;
            }
            else
            {
                double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                newTightenedSL = NormalizeDouble(ask + slDistance, _Digits);
                
                // Respect break-even lock
                if(managedPositions[posIndex].breakEvenLocked && newTightenedSL > entryPrice)
                    newTightenedSL = NormalizeDouble(entryPrice, _Digits);
                
                // Only move SL DOWN (more protective)
                if(currentSL > 0 && newTightenedSL >= currentSL) continue;
                
                // Respect minimum stop distance
                if(newTightenedSL <= ask + minDist) continue;
            }
            
            if(IsSLValid(posType, newTightenedSL))
            {
                if(ModifyPosition(ticket, newTightenedSL, currentTP))
                {
                    LogPrint("+-----------------------------------------+");
                    LogPrint("[SL TIGHTENED] Ticket: ", ticket);
                    LogPrint("Health: ", DoubleToString(health.healthScore, 2),
                             " (ratio: ", DoubleToString(healthRatio, 2), ")");
                    LogPrint("SL: ", currentSL, " -> ", newTightenedSL, 
                             " (ATR dist: ", DoubleToString(slDistance / _Point, 0), " pts)");
                    LogPrint("+-----------------------------------------+");
                }
            }
        }
        
        // 5. PROFIT OFFSET SL TIGHTENING (consecutive wins offset)
        // When consecutive winning trades close while this losing position is open,
        // reduce the max loss exposure by tightening SL proportionally
        if(EnableProfitOffsetSL && profit < 0 
           && managedPositions[posIndex].profitOffsetConsecWins >= ConsecutiveWinsRequired
           && managedPositions[posIndex].profitOffsetAccumulated >= MinOffsetProfit)
        {
            // Calculate original risk from SL
            double origSL = managedPositions[posIndex].profitOffsetOriginalSL;
            
            // Need valid original SL to calculate offset
            if(origSL > 0 && entryPrice > 0)
            {
                // Calculate value per point for this position's lot size
                double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
                double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
                double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
                
                if(tickValue > 0 && tickSize > 0 && point > 0 && volume > 0)
                {
                    double normalizedTickValue = tickValue * volume;
                    double pointsPerTick = tickSize / point;
                    double valuePerPoint = normalizedTickValue / pointsPerTick;
                    
                    // Calculate original SL distance in USD
                    double origSLDistPoints = MathAbs(entryPrice - origSL) / _Point;
                    double origRiskUSD = origSLDistPoints * valuePerPoint;
                    
                    // Calculate new target risk after offset
                    double accumulatedProfit = managedPositions[posIndex].profitOffsetAccumulated;
                    double newTargetRiskUSD = origRiskUSD - accumulatedProfit;
                    
                    // Only proceed if there's meaningful reduction
                    if(newTargetRiskUSD < origRiskUSD && newTargetRiskUSD > 0)
                    {
                        // Convert new target risk back to points
                        double newSLDistPoints = newTargetRiskUSD / valuePerPoint;
                        double newSLDistPrice = newSLDistPoints * _Point;
                        
                        double newOffsetSL = 0;
                        
                        // Re-read position to ensure consistency
                        if(!PositionSelectByTicket(ticket)) continue;
                        currentSL = PositionGetDouble(POSITION_SL);
                        currentTP = PositionGetDouble(POSITION_TP);
                        
                        long offsetStopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
                        double offsetMinDist = offsetStopLevel * _Point;
                        
                        if(posType == POSITION_TYPE_BUY)
                        {
                            double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                            newOffsetSL = NormalizeDouble(entryPrice - newSLDistPrice, _Digits);
                            
                            // Respect break-even lock
                            if(managedPositions[posIndex].breakEvenLocked && newOffsetSL < entryPrice)
                                newOffsetSL = NormalizeDouble(entryPrice, _Digits);
                            
                            // Only tighten (move SL UP), never widen
                            if(currentSL > 0 && newOffsetSL <= currentSL) 
                            {
                                // SL already tighter, skip
                            }
                            else if(newOffsetSL >= bid - offsetMinDist)
                            {
                                // Too close to price, skip
                            }
                            else if(IsSLValid(posType, newOffsetSL))
                            {
                                if(ModifyPosition(ticket, newOffsetSL, currentTP))
                                {
                                    LogPrint("+-----------------------------------------+");
                                    LogPrint("[PROFIT OFFSET SL] Ticket: ", ticket);
                                    LogPrint("Consecutive Wins: ", managedPositions[posIndex].profitOffsetConsecWins,
                                             " | Accumulated: $", DoubleToString(accumulatedProfit, 2));
                                    LogPrint("Original Risk: $", DoubleToString(origRiskUSD, 2),
                                             " -> New Max Risk: $", DoubleToString(newTargetRiskUSD, 2));
                                    LogPrint("SL: ", currentSL, " -> ", newOffsetSL);
                                    LogPrint("+-----------------------------------------+");
                                }
                            }
                        }
                        else // SELL
                        {
                            double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                            newOffsetSL = NormalizeDouble(entryPrice + newSLDistPrice, _Digits);
                            
                            // Respect break-even lock
                            if(managedPositions[posIndex].breakEvenLocked && newOffsetSL > entryPrice)
                                newOffsetSL = NormalizeDouble(entryPrice, _Digits);
                            
                            // Only tighten (move SL DOWN), never widen
                            if(currentSL > 0 && newOffsetSL >= currentSL)
                            {
                                // SL already tighter, skip
                            }
                            else if(newOffsetSL <= ask + offsetMinDist)
                            {
                                // Too close to price, skip
                            }
                            else if(IsSLValid(posType, newOffsetSL))
                            {
                                if(ModifyPosition(ticket, newOffsetSL, currentTP))
                                {
                                    LogPrint("+-----------------------------------------+");
                                    LogPrint("[PROFIT OFFSET SL] Ticket: ", ticket);
                                    LogPrint("Consecutive Wins: ", managedPositions[posIndex].profitOffsetConsecWins,
                                             " | Accumulated: $", DoubleToString(accumulatedProfit, 2));
                                    LogPrint("Original Risk: $", DoubleToString(origRiskUSD, 2),
                                             " -> New Max Risk: $", DoubleToString(newTargetRiskUSD, 2));
                                    LogPrint("SL: ", currentSL, " -> ", newOffsetSL);
                                    LogPrint("+-----------------------------------------+");
                                }
                            }
                        }
                    }
                    // If newTargetRiskUSD <= 0, the accumulated profit exceeds original risk
                    // In this case, try to move SL to break-even (entry price)
                    else if(newTargetRiskUSD <= 0)
                    {
                        if(!PositionSelectByTicket(ticket)) continue;
                        currentSL = PositionGetDouble(POSITION_SL);
                        currentTP = PositionGetDouble(POSITION_TP);
                        
                        double beSL = NormalizeDouble(entryPrice, _Digits);
                        long beStopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
                        double beMinDist = beStopLevel * _Point;
                        bool canApplyBE = false;
                        
                        if(posType == POSITION_TYPE_BUY)
                        {
                            double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
                            canApplyBE = (beSL < bid - beMinDist) && (currentSL == 0 || beSL > currentSL);
                        }
                        else
                        {
                            double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
                            canApplyBE = (beSL > ask + beMinDist) && (currentSL == 0 || beSL < currentSL);
                        }
                        
                        if(canApplyBE && IsSLValid(posType, beSL))
                        {
                            if(ModifyPosition(ticket, beSL, currentTP))
                            {
                                managedPositions[posIndex].breakEvenLocked = true;
                                
                                LogPrint("+-----------------------------------------+");
                                LogPrint("[PROFIT OFFSET SL -> BE] Ticket: ", ticket);
                                LogPrint("Accumulated profit ($", DoubleToString(accumulatedProfit, 2), 
                                         ") >= Original risk ($", DoubleToString(origRiskUSD, 2), ")");
                                LogPrint("SL moved to break-even: ", beSL);
                                LogPrint("+-----------------------------------------+");
                            }
                        }
                    }
                }
            }
        }
        
        // 4. FULL CLOSE + VIRTUAL SL RE-ENTRY (at health threshold)
        if(health.healthScore < MinHealthScore)
        {
            LogPrint("+-----------------------------------------+");
            LogPrint("POSITION EXIT TRIGGERED (Health Decay)");
            LogPrint("Ticket: ", ticket, " | Profit: $", DoubleToString(PositionGetDouble(POSITION_PROFIT), 2));
            LogPrint("Health: ", DoubleToString(health.healthScore, 2), " / ", DoubleToString(MinHealthScore, 2));
            LogPrint("Trend: ", health.trendValid ? "OK" : "FAIL",
                     " | RSI: ", health.momentumValid ? "OK" : "FAIL",
                     " | ATR: ", DoubleToString(health.adverseATR, 1), "x",
                     " | Swing: ", health.swingValid ? "OK" : "FAIL");
            LogPrint("Reason: ", health.reason);
            LogPrint("+-----------------------------------------+");
            
            ClosePosition(ticket);
            
            // Virtual SL + Re-entry: try to re-enter at better price if signal supports it
            if(atlasRuntime.enableVirtualSlReentry)
            {
                TryVirtualSLReentry(posType, initialScore);
            }
        }
    }
}

// +------------------------------------------------------------------+
// | Partial Close Position - Close a portion of position volume      |
// +------------------------------------------------------------------+
bool PartialClosePosition(ulong ticket, double closeVolume)
{
    if(!PositionSelectByTicket(ticket))
    {
        LogPrint("PartialClose: Position ", ticket, " not found");
        return false;
    }
    
    LockOrderSend(true);
    
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
    
    request.action = TRADE_ACTION_DEAL;
    request.position = ticket;
    request.symbol = PositionGetString(POSITION_SYMBOL);
    request.volume = NormalizeVolume(closeVolume);
    request.deviation = 10;
    request.magic = PositionGetInteger(POSITION_MAGIC);
    request.type_filling = GetFillingMode();
    request.type = (type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
    request.price = (type == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    
    if(!OrderSend(request, result))
    {
        LogPrint("PartialClose failed for ", ticket, " Error: ", GetLastError());
        LockOrderSend(false);
        return false;
    }
    
    LogPrint("Partial close ", ticket, " | Vol: ", closeVolume, " | Retcode: ", result.retcode);
    LockOrderSend(false);
    return (result.retcode == TRADE_RETCODE_DONE);
}

// +------------------------------------------------------------------+
// | Virtual SL Re-entry - Re-evaluate and re-enter after exit        |
// +------------------------------------------------------------------+
void TryVirtualSLReentry(ENUM_POSITION_TYPE posType, double initialScore)
{
    if(initialScore <= 0)
        return;

    // Atlas disabled means no new exposure, including virtual-SL re-entry.
    if(!atlasEnabled)
    {
        LogPrint("[ATLAS] Virtual-SL re-entry blocked: Atlas disabled.");
        return;
    }

    // NEW-BAR ENTRY GATE (optional for re-entries)
    // By default re-entries fire intrabar (immediately at the better price). When
    // ReentryRespectsNewBarGate is enabled alongside the effective new-bar-only runtime mode, a re-entry
    // is only allowed once per closed bar — keeping backtests free of intrabar entries.
    if(atlasRuntime.enableNewBarEntryOnly && ReentryRespectsNewBarGate)
    {
        datetime reentryBarTime = iTime(_Symbol, _Period, 0);
        if(lastEntryBarTime == reentryBarTime) return;
    }

    // Check if trading is allowed (respects all guards except duplicate signal filter)
    if(targetEquityReached || minimumEquityReached || minEquityTriggersExceeded) return;
    if(isPaused || isOutsideTradingHours || isLeverageDiffFromInitial) return;
    if(isNearMarketClose) return;
    if(isOrderSendLocked) return;
    if(CountLosingPositions() >= MaxHoldingLossPositions) return;
    if(CountOpenOrders() >= atlasRuntime.maxOpenOrders) return;
    
    // Get current signal strength for the same direction
    ENUM_ORDER_TYPE orderType = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
    SignalStrength strength = GetSignalStrength(orderType);
    
    // Check minimum re-entry threshold
    double minReentryScore = initialScore * ReentryMinSignalPct;
    
    if(strength.finalScore >= minReentryScore)
    {
        // Check direction-specific order enable
        if(posType == POSITION_TYPE_BUY &&
        (!EnableBuyOrders || !atlasBuyEnabled))
        {
            LogPrint("[ATLAS] BUY virtual-SL re-entry blocked.");
            return;
        }

        if(posType == POSITION_TYPE_SELL &&
        (!EnableSellOrders || !atlasSellEnabled))
        {
            LogPrint("[ATLAS] SELL virtual-SL re-entry blocked.");
            return;
        }
        
        LogPrint("+-----------------------------------------+");
        LogPrint("[VIRTUAL SL RE-ENTRY] Re-entering ", posType == POSITION_TYPE_BUY ? "BUY" : "SELL");
        LogPrint("New Signal: ", DoubleToString(strength.finalScore, 1), 
                 " >= Min: ", DoubleToString(minReentryScore, 1),
                 " (", DoubleToString(ReentryMinSignalPct * 100, 0), "% of ", 
                 DoubleToString(initialScore, 1), ")");
        LogPrint("+-----------------------------------------+");
        
        // Open new position at current (better) price
        OpenPosition(orderType, strength.finalScore);

        // Mark this bar as consumed so the gate (and a normal entry this bar) won't double-enter
        if(atlasRuntime.enableNewBarEntryOnly && ReentryRespectsNewBarGate)
            lastEntryBarTime = iTime(_Symbol, _Period, 0);
    }
    else
    {
        LogPrint("[VIRTUAL SL] No re-entry. Signal: ", DoubleToString(strength.finalScore, 1), " < Required: ", DoubleToString(minReentryScore, 1));
    }
}


int CountLosingPositions()
{   
    int count = 0;

    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(ticket == 0) continue;
        
        if(!PositionSelectByTicket(ticket)) continue;
        
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
        
        double profit = PositionGetDouble(POSITION_PROFIT);
        
        if(profit < 0)
        {
            count++;  
        }
    }
    
    return count;
}
// +------------------------------------------------------------------+

// +------------------------------------------------------------------+
// | Manage Trailing TP & SL                                          |
// | Adjusts TP/SL based on signal strength and trails price          |
// +------------------------------------------------------------------+
void ManageTrailingTPSL(ulong ticket)
{   
    if (!EnableTrailing) return;

    if(!PositionSelectByTicket(ticket)) return;

    // Get Position Details
    ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

    // HEDGE CHAIN: skip any leg that belongs to an active chain. The chain logic
    // (ManageHedgeChains) exclusively manages these legs (covered / roll / stop).
    if(atlasRuntime.enableHedgeChain)
    {
        int hpi = GetManagedPositionIndex(ticket);
        if(hpi != -1 && managedPositions[hpi].chainId != 0)
            return;
    }

    double currentSL = PositionGetDouble(POSITION_SL);
    double currentTP = PositionGetDouble(POSITION_TP);
    double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
    double currentPrice = (posType == POSITION_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double profit = PositionGetDouble(POSITION_PROFIT);
    double volume = PositionGetDouble(POSITION_VOLUME);
    
    // Get Signal Strength (smoothed score for management)
    ENUM_ORDER_TYPE orderType = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
    SignalStrength currentStrength = GetSignalStrength(orderType);
    double currentScore = currentStrength.finalScore;
    
    double initialScore = 0;
    int posIndex = GetManagedPositionIndex(ticket);
    if(posIndex != -1)
    {
        initialScore = managedPositions[posIndex].signalScore;
    }
    
    // ADAPTIVE LOGIC (Delta Based)
    double tpAdjustment = 0;
    double slAdjustment = 0;
    string adaptiveReason = "Normal";

    // Calculate score delta (Current - Initial)
    // Positive delta = Signal Strengthened
    // Negative delta = Signal Weakened
    double scoreDelta = currentScore - initialScore;
    
    if(initialScore > 0)
    {
        if(EnableAdaptiveTP) 
        {
             tpAdjustment = scoreDelta * TrailingValueMultiplier;
        }
        
        if(EnableAdaptiveSL) 
        {
             slAdjustment = scoreDelta * TrailingValueMultiplier;
        }
        
        if(MathAbs(scoreDelta) > 0)
        {
            adaptiveReason = "Adaptive (Delta: " + DoubleToString(scoreDelta, 1) + ")";
        }
    }
    
    // TAKE PROFIT MANAGEMENT (Adaptive)
    // Independent R:R owns the TP target: keep it fixed at the entry-set
    // R:R level and skip adaptive recomputation so it isn't overwritten.
    double newTP = currentTP;

    if(EnableTakeProfit && !EnableRiskReward)
    {
        double effectiveTP = TPValue + tpAdjustment;
        
        // Ensure effective TP doesn't go negative or too small
        if(effectiveTP < (TrailingValueMultiplier * 0.1)) effectiveTP = TrailingValueMultiplier * 0.1;

        double tpPoints = ConvertToPoints(TPInputType, effectiveTP, volume);
        double targetTP = 0;
        
        if(posType == POSITION_TYPE_BUY) targetTP = NormalizeDouble(entryPrice + tpPoints * _Point, _Digits);
        else targetTP = NormalizeDouble(entryPrice - tpPoints * _Point, _Digits);
        
        // Only modify if significant difference (> 1 point)
        if(MathAbs(targetTP - currentTP) > _Point)
        {
            newTP = targetTP;
        }
    }

    // TRAILING STOP MANAGEMENT
    double newSL = currentSL; // Default to current
    bool shouldModifySL = false;

    // Filter by profit threshold if enabled (only trail if profit > threshold)
    double profitThreshold = MinBreakEvenProfit * ProfitThresholdMultiplier;
    bool canTrail = (MinBreakEvenProfit <= 0 || !TrailingSLOnProfitableOnly || profit >= profitThreshold);
    
    if(canTrail)
    {
        // Calculate effective Trailing Distance
        double effectiveDist = TrailingDistanceValue + slAdjustment; // Adaptive TS

        // Ensure distance is safe (not negative)
        if(effectiveDist < (TrailingValueMultiplier * 0.1)) effectiveDist = TrailingValueMultiplier * 0.1;

        // Graduated hedge: trail at HedgeTrailATR x ATR (lot-independent). A large hedge
        // lot turns a small dollar-based distance into a near-zero price gap, so the stop
        // lands at market and closes instantly; an ATR distance gives it real room to run.
        double finalTrailingPoints;
        double trailingDistancePrice;
        bool useHedgeTrail = (posIndex != -1 && managedPositions[posIndex].hedgeGraduated && HedgeTrailATR > 0);
        double hedgeAtr = 0;
        if(useHedgeTrail)
        {
            double _bufATR[];
            ArraySetAsSeries(_bufATR, true);
            if(CopyBuffer(atrSignalHandle, 0, 0, 2, _bufATR) >= 2) hedgeAtr = _bufATR[1];
        }

        if(useHedgeTrail && hedgeAtr > 0)
        {
            trailingDistancePrice = HedgeTrailATR * hedgeAtr;
            finalTrailingPoints   = trailingDistancePrice / _Point;
        }
        else
        {
            finalTrailingPoints   = ConvertToPoints(TSInputType, effectiveDist, volume);
            trailingDistancePrice = finalTrailingPoints * _Point;
        }
        
        long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
        long freezeLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
        
        double minStopDistance = stopLevel * _Point;
        double minFreezeDistance = freezeLevel * _Point;
        double minDistance = MathMax(minStopDistance, minFreezeDistance);
        
        double breakEvenPrice = CalculateBreakEvenPrice(ticket, posType, entryPrice, volume);
        
        double calculatedSL = 0;

        // Buy position trailing logic
        if(posType == POSITION_TYPE_BUY)
        {
            double profitPoints = (currentPrice - entryPrice) / _Point;
            if(profitPoints >= finalTrailingPoints) // Use finalTrailingPoints check logic from original
            {
                calculatedSL = currentPrice - trailingDistancePrice;
                double maxAllowedSL = SymbolInfoDouble(_Symbol, SYMBOL_BID) - minDistance;
                
                if(calculatedSL > maxAllowedSL) calculatedSL = maxAllowedSL;
                
                // Break-even lock
                if(TrailingEnableBreakEvenLock && calculatedSL < breakEvenPrice) calculatedSL = breakEvenPrice;
                
                // Only modify if moving UP
                if(currentSL == 0 || calculatedSL > currentSL)
                {
                    if(calculatedSL < SymbolInfoDouble(_Symbol, SYMBOL_BID)) // Safety
                    {
                        newSL = calculatedSL;
                        shouldModifySL = true;
                    }
                }
            }
        }
        // Sell position trailing logic
        else
        {
            double profitPoints = (entryPrice - currentPrice) / _Point;
            if(profitPoints >= finalTrailingPoints)
            {
                calculatedSL = currentPrice + trailingDistancePrice;
                double minAllowedSL = SymbolInfoDouble(_Symbol, SYMBOL_ASK) + minDistance;
                
                if(calculatedSL < minAllowedSL) calculatedSL = minAllowedSL;
                
                // Break-even lock
                if(TrailingEnableBreakEvenLock && calculatedSL > breakEvenPrice) calculatedSL = breakEvenPrice;
                
                // Only modify if moving DOWN
                if(currentSL == 0 || calculatedSL < currentSL)
                {
                    if(calculatedSL > SymbolInfoDouble(_Symbol, SYMBOL_ASK)) // Safety
                    {
                        newSL = calculatedSL;
                        shouldModifySL = true;
                    }
                }
            }
        }
    }

    // HEDGE RECOVERY LOCK: a graduated hedge must never give back below the recovery level
    // (profit = HedgeRecoveryPct% of the older leg's locked loss). Floor the SL at that
    // profit, independent of the trailing gate; trailing still rides the SL above it.
    if(posIndex != -1 && managedPositions[posIndex].hedgeLockProfit > 0)
    {
        double lockProfit = managedPositions[posIndex].hedgeLockProfit;
        double tv = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
        double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
        if(tv > 0 && ts > 0 && volume > 0)
        {
            double lockDist = (lockProfit / volume) * (ts / tv);   // dollars -> price distance
            double bidNow = SymbolInfoDouble(_Symbol, SYMBOL_BID);
            double askNow = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
            double baseSL = shouldModifySL ? newSL : currentSL;

            if(posType == POSITION_TYPE_BUY)
            {
                double lockPrice = NormalizeDouble(entryPrice + lockDist, _Digits);
                // Raise the SL up to the lock (but keep an already-better trailed SL)
                if(lockPrice > baseSL && lockPrice < bidNow)
                {
                    newSL = lockPrice;
                    shouldModifySL = true;
                }
            }
            else
            {
                double lockPrice = NormalizeDouble(entryPrice - lockDist, _Digits);
                // Cap the SL down to the lock (but keep an already-better trailed SL)
                if((baseSL == 0 || lockPrice < baseSL) && lockPrice > askNow)
                {
                    newSL = lockPrice;
                    shouldModifySL = true;
                }
            }
        }
    }

    // Skip if nothing changed
    if(!shouldModifySL && MathAbs(newTP - currentTP) < _Point) return;
    
    // Normalize
    newSL = NormalizeDouble(newSL, _Digits);
    newTP = NormalizeDouble(newTP, _Digits);
    
    // Skip if SL is visually same (if modifier flag was triggered but value didn't change enough - redundant check)
    if(shouldModifySL && MathAbs(newSL - currentSL) < _Point && MathAbs(newTP - currentTP) < _Point) return;

    // Validate new SL
    if(shouldModifySL && !IsSLValid(posType, newSL))
    {
        LogPrint("SL invalid, skipping. Ticket: ", ticket);
        return;
    }

    LogPrint("+-----------------------------------------+");
    LogPrint("POSITION UPDATE (", adaptiveReason, ")");
    LogPrint("Ticket: ", ticket, " | Profit: $", profit);
    LogPrint("Signal: Init=", initialScore, " -> Current=", currentScore, " (Delta: ", scoreDelta, ")");
    if(shouldModifySL) LogPrint("SL: ", currentSL, " -> ", newSL, " (Dist: ", (TrailingDistanceValue + slAdjustment), ")");
    if(MathAbs(newTP - currentTP) > _Point) LogPrint("TP: ", currentTP, " -> ", newTP, " (Base+Adj: ", (TPValue + tpAdjustment), ")");
    LogPrint("+-----------------------------------------+");

    // Try to modify
    if(!ModifyPosition(ticket, newSL, newTP))
    {
        LogPrint("Modify failed. Ticket: ", ticket);
        
        // EMERGENCY CLOSE MECHANISM
        // Trigger if modification failed AND profit is substantial
        // Prevents losing substantial profit due to inability to trail
        
        // Define substantial as 3x minimum target profit
        double minSubstantialProfit = MinBreakEvenProfit * 3.0;

        if(MinBreakEvenProfit > 0 && profit >= minSubstantialProfit)
        {
            LogPrint("!! EMERGENCY CLOSE TRIGGERED !!");
            ClosePosition(ticket);
        }
    }
}
    
// +------------------------------------------------------------------+
// | Positions Management                                             |
// +------------------------------------------------------------------+
// Register managed position with initial score and entry price
void RegisterManagedPosition(ulong ticket, ENUM_POSITION_TYPE type, double signalScore, double entryPrice = 0, ulong chainId = 0, int hedgeLevel = 0, double chainAnchorLoss = 0, int cycleNum = 0)
{
    // Resize array
    ArrayResize(managedPositions, managedPositionCount + 1);

    // Fill position data
    managedPositions[managedPositionCount].ticket = ticket;
    managedPositions[managedPositionCount].type = type;
    managedPositions[managedPositionCount].signalScore = signalScore;
    managedPositions[managedPositionCount].entryPrice = entryPrice;
    managedPositions[managedPositionCount].partialCloseLevel = 0;
    managedPositions[managedPositionCount].breakEvenLocked = false;
    // Initialize profit offset SL tracking
    managedPositions[managedPositionCount].profitOffsetConsecWins = 0;
    managedPositions[managedPositionCount].profitOffsetAccumulated = 0;
    // Initialize hedge chain linkage
    managedPositions[managedPositionCount].chainId = chainId;
    managedPositions[managedPositionCount].hedgeLevel = hedgeLevel;
    managedPositions[managedPositionCount].chainAnchorLoss = chainAnchorLoss;
    managedPositions[managedPositionCount].cycleNum = cycleNum;
    managedPositions[managedPositionCount].noRehedge = false;
    managedPositions[managedPositionCount].hedgeGraduated = false;
    managedPositions[managedPositionCount].hedgeLockProfit = 0;
    // Capture original SL from broker if position exists
    double origSL = 0;
    if(PositionSelectByTicket(ticket)) origSL = PositionGetDouble(POSITION_SL);
    managedPositions[managedPositionCount].profitOffsetOriginalSL = origSL;

    managedPositionCount++;

    LogPrint("Registered position. Ticket: ", ticket,
             " | Type: ", EnumToString(type),
             " | Score: ", signalScore,
             " | Entry: ", entryPrice,
             " | Managed Positions: ", managedPositionCount);
}

// Remove Position from Managed Array
void RemoveManagedPosition(ulong ticket)
{
    for(int i = 0; i < managedPositionCount; i++)
    {
        if(managedPositions[i].ticket == ticket)
        {
            // Shift array elements left
            for(int j = i; j < managedPositionCount - 1; j++)
            {
                managedPositions[j] = managedPositions[j + 1];
            }

            managedPositionCount--;
            ArrayResize(managedPositions, managedPositionCount);

            LogPrint("Removed position: ", ticket,
                     " | Remaining Managed Positions: ", managedPositionCount);
            break;
        }
    }
}

// Sync Managed Positions with Broker (reconciliation fallback)
// OnTradeTransaction is the PRIMARY, event-driven close handler. This per-tick pass
// only catches closes that a transaction event might have missed (e.g. an event lost
// across a restart). Both paths funnel through ProcessClosedPosition, which is
// idempotent, so a single close is never accounted for twice.
void SyncManagedPositions()
{
    for(int i = managedPositionCount - 1; i >= 0; i--)
    {
        if(!PositionSelectByTicket(managedPositions[i].ticket))
        {
            ulong closedTicket = managedPositions[i].ticket;

            // Query deal history to find the closing profit of this position
            double closedProfit = 0;
            bool foundDeal = false;

            // Select history for recent period (last 24 hours should be sufficient)
            datetime fromTime = TimeCurrent() - 86400;
            datetime toTime = TimeCurrent();

            if(HistorySelect(fromTime, toTime))
            {
                int totalDeals = HistoryDealsTotal();
                for(int d = totalDeals - 1; d >= 0; d--)
                {
                    ulong dealTicket = HistoryDealGetTicket(d);
                    if(dealTicket == 0) continue;

                    // Match deal to our position
                    ulong dealPosition = HistoryDealGetInteger(dealTicket, DEAL_POSITION_ID);
                    long dealEntry = HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
                    long dealMagic = HistoryDealGetInteger(dealTicket, DEAL_MAGIC);

                    if(dealPosition == closedTicket && dealEntry == DEAL_ENTRY_OUT && dealMagic == MagicNumber)
                    {
                        closedProfit = HistoryDealGetDouble(dealTicket, DEAL_PROFIT)
                                     + HistoryDealGetDouble(dealTicket, DEAL_SWAP)
                                     + HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
                        foundDeal = true;
                        break;
                    }
                }
            }

            if(foundDeal)
                ProcessClosedPosition(closedTicket, closedProfit);
            else
                RemoveManagedPosition(closedTicket); // no closing deal found — drop the stale entry
        }
    }
}

// +------------------------------------------------------------------+
// | Process a Fully-Closed Managed Position (idempotent)             |
// | Updates the consecutive-loss cooldown and profit-offset tracking |
// | for remaining open positions, then removes the closed position   |
// | from the managed array. Safe to call from both OnTradeTransaction |
// | (primary) and SyncManagedPositions (fallback): the index guard   |
// | ensures each close is accounted for exactly once.                |
// +------------------------------------------------------------------+
void ProcessClosedPosition(ulong closedTicket, double closedProfit)
{
    // Idempotency guard: if it is no longer tracked, this close was already handled
    if(GetManagedPositionIndex(closedTicket) == -1) return;

    // SIGNAL DAMPENING: Track consecutive losses for cooldown
    if(EnableSignalDampening)
    {
        if(closedProfit < 0)
        {
            consecutiveLossCount++;
            LogPrint("[LOSS TRACKER] Position ", closedTicket, " closed at loss: $",
                     DoubleToString(closedProfit, 2),
                     ". Consecutive losses: ", consecutiveLossCount);

            // Activate cooldown after the configured number of consecutive losses
            if(ConsecutiveLossesBeforeCooldown > 0 && consecutiveLossCount >= ConsecutiveLossesBeforeCooldown)
            {
                datetime currBar = iTime(_Symbol, _Period, 0);
                cooldownUntilBarTime = currBar + ConsecutiveLossCooldownBars * PeriodSeconds(_Period);
                LogPrint("[COOLDOWN ACTIVATED] ", consecutiveLossCount,
                         " consecutive losses. No new entries until bar: ",
                         TimeToString(cooldownUntilBarTime));
            }
        }
        else
        {
            if(consecutiveLossCount > 0)
            {
                LogPrint("[LOSS TRACKER] Win streak started. Reset from ",
                         consecutiveLossCount, " consecutive losses.");
            }
            consecutiveLossCount = 0; // Reset on any win
        }
    }

    // PROFIT OFFSET SL: Update tracking on all remaining open positions
    if(EnableProfitOffsetSL)
    {
        for(int p = 0; p < managedPositionCount; p++)
        {
            // Skip the position being removed (closedTicket)
            if(managedPositions[p].ticket == closedTicket) continue;

            // Only track for positions that are currently in loss
            if(!PositionSelectByTicket(managedPositions[p].ticket)) continue;
            double posProfit = PositionGetDouble(POSITION_PROFIT);
            if(posProfit >= 0) continue; // Only for losing positions

            if(closedProfit > 0)
            {
                // Winning trade: accumulate
                managedPositions[p].profitOffsetConsecWins++;
                managedPositions[p].profitOffsetAccumulated += closedProfit;

                LogPrint("[PROFIT OFFSET] Ticket ", managedPositions[p].ticket,
                         " | Win #", managedPositions[p].profitOffsetConsecWins,
                         " | +$", DoubleToString(closedProfit, 2),
                         " | Total: $", DoubleToString(managedPositions[p].profitOffsetAccumulated, 2));
            }
            else
            {
                // Losing trade: reset consecutive counter and accumulated profit
                if(managedPositions[p].profitOffsetConsecWins > 0)
                {
                    LogPrint("[PROFIT OFFSET] Ticket ", managedPositions[p].ticket,
                             " | Consecutive wins reset (closed loss: $",
                             DoubleToString(closedProfit, 2), ")");
                }
                managedPositions[p].profitOffsetConsecWins = 0;
                managedPositions[p].profitOffsetAccumulated = 0;
            }
        }
    }

    RemoveManagedPosition(closedTicket);
}

// Get Managed Position by Ticket    
int GetManagedPositionIndex(ulong ticket)
{
    for(int i = 0; i < managedPositionCount; i++)
    {
        if(managedPositions[i].ticket == ticket)
        {
            return i;
        }
    }
    return -1;
}

// Get Last Position Ticket by Type
// Returns the ticket of the most recently opened position
ulong GetLastPositionTicket(ENUM_POSITION_TYPE type)
{
    ulong lastTicket = 0;
    datetime lastTime = 0;

    for(int i = 0; i < managedPositionCount; i++)
    {
        ulong ticket = managedPositions[i].ticket;
        
        if(managedPositions[i].type != type) continue;

        if(PositionSelectByTicket(ticket))
        {
             datetime posTime = (datetime)PositionGetInteger(POSITION_TIME);
             if(posTime > lastTime)
             {
                 lastTime = posTime;
                 lastTicket = ticket;
             }
        }
    }
    
    return lastTicket;
}

// Open Position
void OpenPosition(ENUM_ORDER_TYPE orderType, double signalScore = 0)
{   
    ENUM_POSITION_TYPE atlasDir = (orderType == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;

    if(!IsAllowedToOpenPosition())
    {
        AtlasSetDecisionReason(atlasDir, atlasLastGlobalBlockReason);
        return;
    }

    if(orderType == ORDER_TYPE_BUY && !atlasBuyEnabled)
    {
        AtlasSetDecisionReason(POSITION_TYPE_BUY, "BUY_DIRECTION_DISABLED");
        LogPrint("[ATLAS] BUY market order blocked.");
        return;
    }

    if(orderType == ORDER_TYPE_SELL && !atlasSellEnabled)
    {
        AtlasSetDecisionReason(POSITION_TYPE_SELL, "SELL_DIRECTION_DISABLED");
        LogPrint("[ATLAS] SELL market order blocked.");
        return;
    }

    LockOrderSend(true);

    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    // Calculate lot size based on equity drop recovery
    // This must be done BEFORE SL/TP conversion so dollar-based values are accurate
    double currentLot = CalculateDynamicLotSize(signalScore);
    
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double price = (orderType == ORDER_TYPE_BUY) ? ask : bid;
    
    request.action = TRADE_ACTION_DEAL;
    request.symbol = _Symbol;
    request.volume = currentLot;
    request.type = orderType;
    request.price = price;
    request.deviation = 10;
    request.magic = MagicNumber;
    request.comment = "Open Position by Nyao Scalper";
    request.type_filling = GetFillingMode();

    // Resolve SL (risk) and TP distances. Independent R:R mode overrides
    // both manual SL and manual TP; otherwise the manual settings apply.
    double slPoints = GetSLPoints(currentLot);
    double tpPoints = GetTPPoints(currentLot);

    if(slPoints > 0)
    {
        if(orderType == ORDER_TYPE_BUY)
            request.sl = NormalizeDouble(price - (slPoints * _Point), _Digits);
        else
            request.sl = NormalizeDouble(price + (slPoints * _Point), _Digits);
    }

    if(tpPoints > 0)
    {
        if(orderType == ORDER_TYPE_BUY)
            request.tp = NormalizeDouble(price + (tpPoints * _Point), _Digits);
        else
            request.tp = NormalizeDouble(price - (tpPoints * _Point), _Digits);
    }

    AtlasBeginOrderAttempt(orderType, "MARKET");
    bool orderResult = OrderSend(request, result);
    atlasLastOrderRetcode = (long)result.retcode;
    
    if(orderResult)
    {
        if(result.retcode == TRADE_RETCODE_DONE)
        {   
            atlasLastOrderSuccess = true;
            atlasLastOrderTicket = result.order;
            AtlasSetDecisionReason(atlasDir, "ORDER_OPENED", true);
            double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
            double equityDropAmount = lastPeakEquity - currentEquity;
            
            double equityDropPercentage = 0;
            if(lastPeakEquity > 0)
            {
                equityDropPercentage = (equityDropAmount / lastPeakEquity) * 100.0;
            }
            
            LogPrint("Order opened successfully. Ticket: ", result.order, 
                     ", Type: ", orderType == ORDER_TYPE_BUY ? "BUY" : "SELL",
                     ", Lot Size: ", currentLot,
                     ", Signal Score: ", signalScore,
                     " (Peak: $", lastPeakEquity, 
                     ", Current: $", currentEquity,
                     ", Drop: ", equityDropPercentage, "%)");
            
            if(request.sl > 0)
            {
                LogPrint(" | SL: ", request.sl);
            }
            if(request.tp > 0)
            {
                LogPrint(" | TP: ", request.tp, EnableRiskReward ? StringFormat(" (R:R 1:%.2f)", RiskRewardRatio) : "");
            }
            
            // Register position to managed array
            ENUM_POSITION_TYPE posType = (orderType == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
            RegisterManagedPosition(result.order, posType, signalScore, price);
            
            // Update Candle Counters
            datetime currBarTime = iTime(_Symbol, _Period, 0);
            if(currentBarTime != currBarTime)
            {
                currentBarTime = currBarTime;
                buysOnCurrentBar = 0;
                sellsOnCurrentBar = 0;
            }
            
            if(orderType == ORDER_TYPE_BUY) buysOnCurrentBar++;
            else sellsOnCurrentBar++;
            
            // Update global last position tracking
            if(orderType == ORDER_TYPE_BUY)
            {
                lastBuyTime = TimeCurrent();
                lastBuyPrice = price;
            }
            else
            {
                lastSellTime = TimeCurrent();
                lastSellPrice = price;
            }
        }
        else
        {
            AtlasSetDecisionReason(atlasDir, "ORDER_REJECTED");
            LogPrint("Order failed. Return code: ", result.retcode);
        }
    }
    else
    {
        atlasLastOrderRetcode = (long)result.retcode;
        AtlasSetDecisionReason(atlasDir, "ORDER_SEND_ERROR");
        LogPrint("OrderSend error: ", GetLastError());
    }

    LockOrderSend(false);
}

// +------------------------------------------------------------------+
// | Compute the Lot Needed to Recover the Older Leg                   |
// | Sizes the hedge so that, after a favorable move of                |
// | HedgeRecoveryATR x ATR, its profit covers HedgeRecoveryPct% of    |
// | the older leg's loss - accounting for the older leg continuing to |
// | bleed over that same move. Money<->price uses the EA's standard   |
// | tickValue/tickSize convention.                                    |
// |   lot = p*olderLot + p*loss / (moneyGainedPerLotOverTargetMove)   |
// | Returns 0 if it cannot be computed (caller falls back).           |
// +------------------------------------------------------------------+
double ComputeRecoveryLot(double olderLot, double olderLoss, double atr)
{
    double p = HedgeRecoveryPct / 100.0;
    if(p <= 0) p = 1.0;

    double tickValue  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double targetPrice = HedgeRecoveryATR * atr;       // favorable move (price units) to recover within
    if(tickValue <= 0 || tickSize <= 0 || targetPrice <= 0) return 0;

    // Money gained per 1.0 lot over the target favorable move
    double moneyPerLot = (targetPrice / tickSize) * tickValue;
    if(moneyPerLot <= 0) return 0;

    // p*olderLot outpaces the older leg's continued bleed; the second term funds the loss.
    return p * olderLot + p * olderLoss / moneyPerLot;
}

// +------------------------------------------------------------------+
// | Decide the Hedge Lot for the Next Leg                            |
// | Auto-recover sizing (default) or fixed multiplier, then clamped   |
// | to HedgeMaxLot and broker volume limits.                          |
// +------------------------------------------------------------------+
double ComputeHedgeLot(double olderLot, double olderLoss, double atr)
{
    double lot = 0;
    if(HedgeAutoLot)
        lot = ComputeRecoveryLot(olderLot, olderLoss, atr);

    // Fallback to fixed multiplier if auto-size is off or could not be computed
    if(lot <= 0)
        lot = olderLot * HedgeLotMultiplier;

    // The hedge must exceed the older leg, otherwise the opposite-direction pair has
    // no net recovery power. Use one volume step above as the hard minimum.
    double stepVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double minLot = olderLot + (stepVol > 0 ? stepVol : 0.01);
    if(lot < minLot) lot = minLot;

    if(HedgeMaxLot > 0 && lot > HedgeMaxLot) lot = HedgeMaxLot;
    return NormalizeVolume(lot);
}

// +------------------------------------------------------------------+
// | Open One Rolling-Hedge Leg                                        |
// | Reversed market order at the pre-computed hedgeLot. Opened NAKED   |
// | (no SL/TP): chain logic closes it. Registers the leg under the    |
// | shared chainId at the given level, carrying the anchor loss        |
// | forward. Bypasses IsAllowedToOpenPosition / MaxOpenOrders.        |
// | Returns the new ticket, or 0 on failure.                          |
// +------------------------------------------------------------------+
ulong OpenChainHedge(ulong chainId, ENUM_POSITION_TYPE prevType, double hedgeLot, int newLevel, double anchorLoss, int cycleNum)
{
    LockOrderSend(true);

    MqlTradeRequest request = {};
    MqlTradeResult result = {};

    // Reverse the previous leg's direction (chain alternates BUY/SELL)
    ENUM_ORDER_TYPE hedgeOrderType = (prevType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;

    hedgeLot = NormalizeVolume(hedgeLot);

    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double price = (hedgeOrderType == ORDER_TYPE_BUY) ? ask : bid;

    request.action = TRADE_ACTION_DEAL;
    request.symbol = _Symbol;
    request.volume = hedgeLot;
    request.type = hedgeOrderType;
    request.price = price;
    request.deviation = 10;
    request.magic = MagicNumber;
    request.comment = "Hedge L" + IntegerToString(newLevel) + " by Nyao Scalper";
    request.type_filling = GetFillingMode();

    // NAKED: no SL/TP. The chain's covered / roll / stop logic closes it.

    ulong newTicket = 0;
    bool orderResult = OrderSend(request, result);

    if(orderResult && result.retcode == TRADE_RETCODE_DONE)
    {
        ENUM_POSITION_TYPE hedgePosType = (hedgeOrderType == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;
        RegisterManagedPosition(result.order, hedgePosType, 0, price, chainId, newLevel, anchorLoss, cycleNum);
        newTicket = result.order;

        LogPrint("+-----------------------------------------+");
        LogPrint("[HEDGE CHAIN] Opened hedge L", newLevel, " | Chain: ", chainId, " | Cycle: ", cycleNum);
        LogPrint("Leg ", result.order, " (", EnumToString(hedgePosType), ")",
                 " | Lot: ", hedgeLot, " | Sizing: ", (HedgeAutoLot ? "Auto-Recover" : "Fixed x" + DoubleToString(HedgeLotMultiplier, 2)));
        LogPrint("+-----------------------------------------+");
    }
    else
    {
        LogPrint("[HEDGE CHAIN] OrderSend failed. Retcode: ", result.retcode, " | Error: ", GetLastError());
    }

    LockOrderSend(false);
    return newTicket;
}

// +------------------------------------------------------------------+
// | Graduate a Leg out of Its Chain                                   |
// | Clears the chain flags so normal trailing / loss management take  |
// | over (used when a hedge has covered the loss and should be        |
// | trailed, or when only a single orphan leg remains).               |
// +------------------------------------------------------------------+
void GraduateChainLeg(ulong ticket)
{
    int idx = GetManagedPositionIndex(ticket);
    if(idx == -1) return;
    managedPositions[idx].chainId         = 0;
    managedPositions[idx].hedgeLevel      = 0;
    managedPositions[idx].chainAnchorLoss = 0;
    managedPositions[idx].cycleNum        = 0;
    managedPositions[idx].hedgeGraduated  = true;   // trail this big-lot leg with HedgeTrailATR
    managedPositions[idx].hedgeLockProfit = 0;      // caller sets a recovery floor if applicable
}

// +------------------------------------------------------------------+
// | Close Every Open Leg of a Hedge Chain                            |
// +------------------------------------------------------------------+
void CloseChain(ulong chainId)
{
    for(int z = managedPositionCount - 1; z >= 0; z--)
    {
        if(managedPositions[z].chainId != chainId) continue;
        if(PositionSelectByTicket(managedPositions[z].ticket))
            ClosePosition(managedPositions[z].ticket);
    }
}

// +------------------------------------------------------------------+
// | Release an exhausted chain to adaptive loss management            |
// | When a chain can no longer expand (max cycles / lot ceiling), it  |
// | is NOT force-closed: every leg is handed back to normal trailing  |
// | + loss management and flagged noRehedge so no new chain starts on |
// | it. The legs then resolve via health close / partial / trailing,  |
// | and (being chainId 0 again) are re-covered by the basket stop.    |
// +------------------------------------------------------------------+
void ReleaseChainToLossMgmt(ulong chainId)
{
    int released = 0;
    for(int z = 0; z < managedPositionCount; z++)
    {
        if(managedPositions[z].chainId != chainId) continue;
        managedPositions[z].chainId         = 0;
        managedPositions[z].hedgeLevel      = 0;
        managedPositions[z].chainAnchorLoss = 0;
        managedPositions[z].cycleNum        = 0;
        managedPositions[z].noRehedge       = true;   // exhausted - do not hedge these again
        managedPositions[z].hedgeGraduated  = true;   // trail these big-lot legs with HedgeTrailATR
        released++;
    }
    LogPrint("[HEDGE CHAIN] Released chain ", chainId, " (", released,
             " legs) to adaptive loss management - no re-hedge.");
}

// +------------------------------------------------------------------+
// | Effective chain-loss stop ($): combines the fixed-$ and          |
// | %-of-equity caps. Returns the tighter (smaller) of whichever are  |
// | enabled, or 0 if neither is set.                                  |
// +------------------------------------------------------------------+
double ChainLossStopThreshold()
{
    double usd = (HedgeMaxChainLossUSD > 0) ? HedgeMaxChainLossUSD : 0;
    double pct = (HedgeMaxChainLossPct > 0)
                 ? AccountInfoDouble(ACCOUNT_EQUITY) * HedgeMaxChainLossPct / 100.0
                 : 0;
    if(usd > 0 && pct > 0) return MathMin(usd, pct);
    return MathMax(usd, pct);
}

// +------------------------------------------------------------------+
// | Reseed a new cycle when a roll can't proceed (cycle level limit   |
// | or lot ceiling). Closes the recovered older leg, partial-closes   |
// | the deepest hedge by HedgeCyclePartialPct%, makes the reduced      |
// | hedge the level-0 root of a NEW cycle, and opens a fresh L1 to     |
// | recover it. Returns false if the hedge can't be reduced.          |
// +------------------------------------------------------------------+
bool ReseedCycle(ulong id, ulong olderTicket, ulong hedgeTicket, double hedgeLot,
                 ENUM_POSITION_TYPE hedgeType, int cycleNum, double atr)
{
    double minL = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    if(step <= 0) step = 0.01;

    double closeVol = MathFloor((hedgeLot * HedgeCyclePartialPct / 100.0) / step) * step;
    double remaining = hedgeLot - closeVol;
    if(remaining < minL)
    {
        closeVol  = MathFloor((hedgeLot - minL) / step) * step;
        remaining = hedgeLot - closeVol;
    }
    if(closeVol < minL || remaining < minL)
        return false;                                   // can't reduce meaningfully

    // 1) Partial-close the deepest hedge FIRST (shrink exposure). If it fails, leave the
    //    chain fully INTACT (older not yet closed) and bail so the caller releases both
    //    legs cleanly to loss management - never a half-dismantled chain.
    if(!PartialClosePosition(hedgeTicket, closeVol))
    {
        LogPrint("[HEDGE CHAIN RESEED] Partial close failed for ", hedgeTicket,
                 " - chain left intact, releasing to loss management.");
        return false;
    }

    // 2) Close the recovered older leg (free / near breakeven)
    if(olderTicket != 0) ClosePosition(olderTicket);

    // 3) Re-read the reduced hedge -> becomes the new cycle's level-0 root
    if(!PositionSelectByTicket(hedgeTicket)) return false;
    double remLot = PositionGetDouble(POSITION_VOLUME);
    double remPL  = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
    double newAnchor = (remPL < 0) ? -remPL : 0.01;

    int idx = GetManagedPositionIndex(hedgeTicket);
    if(idx == -1) return false;
    managedPositions[idx].chainId         = hedgeTicket;   // new cycle id = this ticket
    managedPositions[idx].hedgeLevel      = 0;
    managedPositions[idx].chainAnchorLoss = newAnchor;
    managedPositions[idx].cycleNum        = cycleNum + 1;

    LogPrint("+-----------------------------------------+");
    LogPrint("[HEDGE CHAIN RESEED] New cycle ", cycleNum + 1, " | Chain ", id);
    LogPrint("Closed older ", olderTicket, "; closed ", DoubleToString(closeVol, 2),
             " of hedge ", hedgeTicket, " (remain ", DoubleToString(remLot, 2),
             ", anchor $", DoubleToString(newAnchor, 2), ")");
    LogPrint("+-----------------------------------------+");

    // 4) Open a fresh L1 hedge to recover the reduced root
    double hLot = ComputeHedgeLot(remLot, newAnchor, atr);
    if(hLot > remLot)
        OpenChainHedge(hedgeTicket, hedgeType, hLot, 1, newAnchor, cycleNum + 1);
    else
        LogPrint("[HEDGE CHAIN RESEED] Reduced root still can't be hedged within lot ceiling - holding as free leg.");

    return true;
}

// +------------------------------------------------------------------+
// | Manage Hedge Chains (Rolling Martingale Recovery)                |
// | A "chain" keeps at most TWO open legs: the OLDER leg (being       |
// | hedged) and its HEDGE (newer, larger, opposite direction).        |
// |                                                                   |
// |  - COVERED : hedge profit >= HedgeRecoveryPct% of the older leg's |
// |              current loss -> close older, trail the hedge. End.   |
// |  - ROLL    : hedge losing AND older recovered to >= roll min ->    |
// |              close older (free), open a bigger reverse hedge, up   |
// |              to HedgeCycleLevels per cycle.                        |
// |  - RESEED  : at the cycle level limit OR lot ceiling -> close      |
// |              older, partial-close the deepest hedge by             |
// |              HedgeCyclePartialPct%, start a NEW cycle from the      |
// |              reduced leg (up to HedgeMaxCycles cycles).            |
// |  - STOP    : combined chain loss >= HedgeMaxChainLoss($/%) -> close.|
// |                                                                   |
// | WARNING: martingale - lots grow each roll; ranging markets can    |
// | compound drawdown. Bounded by cycle caps / HedgeMaxLot / stop.    |
// +------------------------------------------------------------------+
void ManageHedgeChains()
{
    if(!atlasRuntime.enableHedgeChain) return;

    // Current ATR (closed-candle [1] for stability, matching ManageLosingPositions)
    double bufATR[];
    ArraySetAsSeries(bufATR, true);
    if(CopyBuffer(atrSignalHandle, 0, 0, 2, bufATR) < 2) return;
    double atr = bufATR[1];
    if(atr <= 0) return;

    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

    // ---- Collect distinct chain ids currently in the managed array ----
    ulong chains[];
    int chainCount = 0;
    for(int i = 0; i < managedPositionCount; i++)
    {
        ulong id = managedPositions[i].chainId;
        if(id == 0) continue;
        bool seen = false;
        for(int k = 0; k < chainCount; k++) if(chains[k] == id) { seen = true; break; }
        if(!seen) { ArrayResize(chains, chainCount + 1); chains[chainCount++] = id; }
    }

    // ---- Phase A: manage each existing chain (rolling pair) ----
    for(int c = 0; c < chainCount; c++)
    {
        ulong id = chains[c];

        // Identify the OLDER leg (lowest level) and the HEDGE (highest level).
        ulong olderTicket = 0, hedgeTicket = 0;
        int olderLevel = INT_MAX, hedgeLevel = -1;
        double olderPL = 0, hedgePL = 0;
        double hedgeLot = 0;
        ENUM_POSITION_TYPE hedgeType = POSITION_TYPE_BUY;
        double anchorLoss = 0;
        int openLegs = 0;
        int cycleNum = 0;
        double totalPL = 0;

        for(int i = 0; i < managedPositionCount; i++)
        {
            if(managedPositions[i].chainId != id) continue;
            ulong t = managedPositions[i].ticket;
            if(!PositionSelectByTicket(t)) continue;       // leg already gone
            openLegs++;
            double pl = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
            totalPL += pl;
            int lvl = managedPositions[i].hedgeLevel;
            cycleNum = managedPositions[i].cycleNum;
            if(managedPositions[i].chainAnchorLoss > 0) anchorLoss = managedPositions[i].chainAnchorLoss;

            if(lvl < olderLevel) { olderLevel = lvl; olderTicket = t; olderPL = pl; }
            if(lvl > hedgeLevel)
            {
                hedgeLevel = lvl;
                hedgeTicket = t;
                hedgePL = pl;
                hedgeLot = PositionGetDouble(POSITION_VOLUME);
                hedgeType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
            }
        }

        // No legs left, or only one (orphan / transient): graduate the survivor
        // back to normal management and let the chain dissolve.
        if(openLegs == 0) continue;
        if(openLegs == 1)
        {
            if(hedgeTicket != 0) GraduateChainLeg(hedgeTicket);
            continue;
        }

        // COVERED: hedge profit covers the older leg's current loss -> close older, trail hedge.
        if(olderPL < 0)
        {
            double olderLoss = -olderPL;
            double coverNeeded = (HedgeRecoveryPct / 100.0) * olderLoss;
            if(hedgePL >= coverNeeded)
            {
                LogPrint("+-----------------------------------------+");
                LogPrint("[HEDGE CHAIN COVERED] Chain ", id);
                LogPrint("Hedge ", hedgeTicket, " profit $", DoubleToString(hedgePL, 2),
                         " >= ", DoubleToString(HedgeRecoveryPct, 0), "% of older ", olderTicket,
                         " loss $", DoubleToString(olderLoss, 2));
                LogPrint("Closing older leg; hedge graduates and trails (SL floored at recovery).");
                LogPrint("+-----------------------------------------+");
                ClosePosition(olderTicket);
                GraduateChainLeg(hedgeTicket);
                // Recovery floor: keep at least coverNeeded profit locked on the hedge so the
                // pair never gives back below the HedgeRecoveryPct net. Trailing rides above it.
                int hgi = GetManagedPositionIndex(hedgeTicket);
                if(hgi != -1) managedPositions[hgi].hedgeLockProfit = coverNeeded;
                continue;
            }
        }

        // ROLL: hedge losing AND older recovered -> close older (free), open next hedge.
        if(hedgePL < 0 && olderPL >= HedgeRollMinProfit)
        {
            // A normal roll needs BOTH: room in the cycle (level cap) AND a strictly
            // larger hedge (lot ceiling). If either fails, reseed a new cycle instead.
            bool   levelOk = (hedgeLevel < HedgeCycleLevels);
            double newLot  = levelOk ? ComputeHedgeLot(hedgeLot, -hedgePL, atr) : 0;
            bool   lotOk   = (newLot > hedgeLot);

            if(levelOk && lotOk)
            {
                LogPrint("+-----------------------------------------+");
                LogPrint("[HEDGE CHAIN ROLL] Chain ", id, " | Cycle ", cycleNum);
                LogPrint("Older ", olderTicket, " recovered to $", DoubleToString(olderPL, 2),
                         "; hedge ", hedgeTicket, " losing $", DoubleToString(hedgePL, 2));
                LogPrint("Closing older; opening hedge L", hedgeLevel + 1, " (lot ",
                         DoubleToString(newLot, 2), " > ", DoubleToString(hedgeLot, 2), ").");
                LogPrint("+-----------------------------------------+");
                ClosePosition(olderTicket);
                OpenChainHedge(id, hedgeType, newLot, hedgeLevel + 1, anchorLoss, cycleNum);
                continue;
            }

            // Cannot roll within this cycle (level cap or lot ceiling) -> reseed or stop.
            string why = (!levelOk) ? "cycle level limit" : "lot ceiling";
            bool cyclesLeft = (HedgeMaxCycles <= 0 || cycleNum + 1 < HedgeMaxCycles);

            if(EnableHedgeCycleReset && cyclesLeft)
            {
                LogPrint("[HEDGE CHAIN] Chain ", id, " cyc ", cycleNum, ": ", why,
                         " reached -> partial-close & reseed new cycle.");
                if(!ReseedCycle(id, olderTicket, hedgeTicket, hedgeLot, hedgeType, cycleNum, atr))
                {
                    LogPrint("[HEDGE CHAIN] Reseed failed (cannot reduce hedge) -> release to loss mgmt.");
                    ReleaseChainToLossMgmt(id);
                }
                continue;
            }
            else
            {
                // Chain exhausted (max cycles / lot ceiling with reseed off). Do NOT close:
                // hand the legs to adaptive loss management and stop hedging them.
                LogPrint("[HEDGE CHAIN EXHAUSTED] Chain ", id, " cyc ", cycleNum, ": ", why, ", ",
                         (!EnableHedgeCycleReset ? "reseed disabled" : "max cycles reached"),
                         " -> release to adaptive loss management (no re-hedge).");
                ReleaseChainToLossMgmt(id);
                continue;
            }
        }

        // STOP: total open loss across the chain exceeds the backstop ($ and/or % equity;
        // the tighter threshold wins) -> close every leg.
        double stopThr = ChainLossStopThreshold();
        if(stopThr > 0 && totalPL <= -stopThr)
        {
            LogPrint("+-----------------------------------------+");
            LogPrint("[HEDGE CHAIN STOPPED] Chain ", id, " | Open legs: ", openLegs);
            LogPrint("Total loss $", DoubleToString(totalPL, 2), " <= stop $", DoubleToString(-stopThr, 2));
            LogPrint("Closing all chain legs (loss backstop).");
            LogPrint("+-----------------------------------------+");
            CloseChain(id);
            continue;
        }
        // Otherwise hold and wait for price to resolve the pair.
    }

    // ---- Phase B: start a new chain for a qualifying standalone losing position ----
    for(int i = 0; i < managedPositionCount; i++)
    {
        if(managedPositions[i].chainId != 0) continue;     // already in a chain
        if(managedPositions[i].noRehedge) continue;        // exhausted chain leg - left to loss mgmt

        ulong ticket = managedPositions[i].ticket;
        if(!PositionSelectByTicket(ticket)) continue;
        if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
        if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;

        double pl = PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
        if(pl >= 0) continue;                              // not losing

        ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
        double entryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
        double volume = PositionGetDouble(POSITION_VOLUME);
        double curTP = PositionGetDouble(POSITION_TP);
        double curSL = PositionGetDouble(POSITION_SL);

        double adverse = (posType == POSITION_TYPE_BUY) ? (entryPrice - bid) : (ask - entryPrice);
        if(adverse <= 0) continue;
        if((adverse / atr) < HedgeTriggerATR) continue;

        // ANTI-SPIKE: only hedge if the REVERSE direction's signal score confirms the move.
        // A wick/spike that crosses the ATR trigger intrabar but isn't a real reversal will
        // not have a strong opposite-direction score, so no doubled hedge is opened. If the
        // reversal is genuine the score builds up and the hedge fires on a later tick; if it
        // was a spike the position recovers and no hedge is needed.
        if(HedgeRequireSignal)
        {
            ENUM_ORDER_TYPE hedgeDir = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            double hedgeScore = GetSignalStrength(hedgeDir).finalScore;
            if(hedgeScore < HedgeMinSignalScore)
            {
                LogPrint("[HEDGE CHAIN] Skip start for ", ticket, ": reverse signal ",
                         DoubleToString(hedgeScore, 2), " < ", DoubleToString(HedgeMinSignalScore, 2),
                         " (likely spike) - waiting for confirmation.");
                continue;
            }
        }

        double anchorLoss = -pl;                           // positive loss magnitude at chain start

        // Size the first hedge to recover the original's loss. Only start the chain if
        // that hedge can be strictly larger than the original - otherwise the pair would
        // freeze (equal opposite lots never recover). If the original is already at/above
        // HedgeMaxLot, leave it to normal loss management instead of starting a doomed chain.
        double hedgeLot = ComputeHedgeLot(volume, anchorLoss, atr);
        if(hedgeLot <= volume)
        {
            LogPrint("[HEDGE CHAIN] Skip start for ", ticket, ": hedge lot ", DoubleToString(hedgeLot, 2),
                     " not > position lot ", DoubleToString(volume, 2), " (HedgeMaxLot ",
                     DoubleToString(HedgeMaxLot, 2), "). Left to normal management.");
            continue;
        }

        // Promote this position to the first leg (level 0, cycle 0) of a new chain.
        managedPositions[i].chainId         = ticket;
        managedPositions[i].hedgeLevel      = 0;
        managedPositions[i].chainAnchorLoss = anchorLoss;
        managedPositions[i].cycleNum        = 0;
        managedPositions[i].hedgeGraduated  = false;   // active chain leg again, not a graduated trailer
        managedPositions[i].hedgeLockProfit = 0;

        // Clear the first position's SL so the chain logic alone governs it (optional).
        if(HedgeClearRootSL && curSL != 0) ModifyPosition(ticket, 0, curTP);

        LogPrint("+-----------------------------------------+");
        LogPrint("[HEDGE CHAIN STARTED] First leg ", ticket, " (", EnumToString(posType), ")");
        LogPrint("Start loss: $", DoubleToString(anchorLoss, 2),
                 " | Adverse: ", DoubleToString(adverse / atr, 2), " ATR >= ", DoubleToString(HedgeTriggerATR, 2));
        LogPrint("+-----------------------------------------+");

        // Open the first hedge (level 1) against this losing position.
        OpenChainHedge(ticket, posType, hedgeLot, 1, anchorLoss, 0);
    }
}

// +------------------------------------------------------------------+
// | Compute Pullback Limit Entry Price for a Direction                |
// | Honors LimitEntryAnchor:                                          |
// |   FIXED_ATR : flat depth = LimitEntryATRFraction * ATR            |
// |   EMA       : anchor at the fast EMA                              |
// |   SWING     : anchor at the recent swing low/high (structure)     |
// |   SMART     : nearer-to-price of swing/EMA                        |
// | The structural modes are capped no deeper than the ATR fraction   |
// | and always clamped to the broker stop level. Falls back to the    |
// | fixed depth when no valid level sits on the pullback side.        |
// | Returns 0 on data error.                                          |
// +------------------------------------------------------------------+
double ComputeLimitEntryPrice(ENUM_ORDER_TYPE dir, double atr)
{
    bool isBuy = (dir == ORDER_TYPE_BUY);
    double ref = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);

    long stopLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
    double minStopDist = stopLevel * _Point;
    double maxDist = atr * LimitEntryATRFraction;          // ATR cap / fixed depth
    if(maxDist <= 0) return 0;

    double fixedDepthPrice = isBuy ? (ref - maxDist)     : (ref + maxDist);      // deepest allowed
    double minDistPrice    = isBuy ? (ref - minStopDist) : (ref + minStopDist);  // shallowest allowed

    // FIXED_ATR: flat depth, no structural anchor (clamp to broker stop level)
    if(LimitEntryAnchor == LIMIT_ANCHOR_FIXED_ATR)
    {
        double pf = isBuy ? MathMin(fixedDepthPrice, minDistPrice)
                          : MathMax(fixedDepthPrice, minDistPrice);
        return NormalizeDouble(pf, _Digits);
    }

    // Gather structural anchors on the pullback side of price
    // ("nearer to price" = max for buy, min for sell)
    double anchor = isBuy ? -DBL_MAX : DBL_MAX;
    bool haveAnchor = false;

    // Fast EMA (current value)
    if(LimitEntryAnchor == LIMIT_ANCHOR_EMA || LimitEntryAnchor == LIMIT_ANCHOR_SMART)
    {
        double bufEMA[];
        ArraySetAsSeries(bufEMA, true);
        if(CopyBuffer(emaFastHandle, 0, 0, 1, bufEMA) >= 1)
        {
            double ema = bufEMA[0];
            if(isBuy ? (ema < ref) : (ema > ref))
            {
                anchor = isBuy ? MathMax(anchor, ema) : MathMin(anchor, ema);
                haveAnchor = true;
            }
        }
    }

    // Swing level over the health swing lookback
    if(LimitEntryAnchor == LIMIT_ANCHOR_SWING || LimitEntryAnchor == LIMIT_ANCHOR_SMART)
    {
        int look = MathMax(5, HealthSwingLookback);
        MqlRates rates[];
        ArraySetAsSeries(rates, true);
        int copied = CopyRates(_Symbol, _Period, 1, look, rates);
        if(copied > 0)
        {
            double sw = isBuy ? rates[0].low : rates[0].high;
            for(int j = 1; j < copied; j++)
                sw = isBuy ? MathMin(sw, rates[j].low) : MathMax(sw, rates[j].high);
            if(isBuy ? (sw < ref) : (sw > ref))
            {
                anchor = isBuy ? MathMax(anchor, sw) : MathMin(anchor, sw);
                haveAnchor = true;
            }
        }
    }

    // No valid anchor on the pullback side -> fall back to fixed depth
    double price = haveAnchor ? anchor : fixedDepthPrice;

    // Cap: never deeper than the ATR fraction...
    price = isBuy ? MathMax(price, fixedDepthPrice) : MathMin(price, fixedDepthPrice);
    // ...and always respect the broker stop level (this bound wins)
    price = isBuy ? MathMin(price, minDistPrice) : MathMax(price, minDistPrice);

    return NormalizeDouble(price, _Digits);
}

// +------------------------------------------------------------------+
// | Place Pending Limit Entry (pullback) - fresh entries only        |
// | Used when EnableLimitEntry is on. The resulting position is       |
// | registered at FILL time via OnTradeTransaction (DEAL_ENTRY_IN);   |
// | the entry-thesis score is stashed in the order comment so it      |
// | survives until the fill. Virtual-SL re-entries never come here.   |
// +------------------------------------------------------------------+
void PlaceLimitEntry(ENUM_ORDER_TYPE dir, double signalScore)
{
    ENUM_POSITION_TYPE atlasDir = (dir == ORDER_TYPE_BUY) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;

    if(!IsAllowedToOpenPosition())
    {
        AtlasSetDecisionReason(atlasDir, atlasLastGlobalBlockReason);
        return;
    }

    if(dir == ORDER_TYPE_BUY && !atlasBuyEnabled)
    {
        AtlasSetDecisionReason(POSITION_TYPE_BUY, "BUY_DIRECTION_DISABLED");
        LogPrint("[ATLAS] BUY limit order blocked.");
        return;
    }

    if(dir == ORDER_TYPE_SELL && !atlasSellEnabled)
    {
        AtlasSetDecisionReason(POSITION_TYPE_SELL, "SELL_DIRECTION_DISABLED");
        LogPrint("[ATLAS] SELL limit order blocked.");
        return;
    }

    // One working pending at a time (one entry decision per signal)
    if(CountWorkingLimitOrders() > 0)
    {
        AtlasSetDecisionReason(atlasDir, "WORKING_LIMIT_EXISTS");
        return;
    }

    // Current ATR drives both the fixed depth and the cap for structural anchors
    double bufATR[];
    ArraySetAsSeries(bufATR, true);
    if(CopyBuffer(atrSignalHandle, 0, 0, 1, bufATR) < 1) { AtlasSetDecisionReason(atlasDir, "ATR_UNAVAILABLE"); return; }
    double atr = bufATR[0];
    if(atr <= 0) { AtlasSetDecisionReason(atlasDir, "ATR_INVALID"); return; }

    double entry = ComputeLimitEntryPrice(dir, atr);
    if(entry <= 0) { AtlasSetDecisionReason(atlasDir, "LIMIT_PRICE_INVALID"); return; }

    double currentLot = CalculateDynamicLotSize(signalScore);
    double ref = (dir == ORDER_TYPE_BUY) ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                                         : SymbolInfoDouble(_Symbol, SYMBOL_BID);

    LockOrderSend(true);

    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    request.action = TRADE_ACTION_PENDING;
    request.symbol = _Symbol;
    request.volume = currentLot;
    request.deviation = 10;
    request.magic = MagicNumber;
    request.type_time = ORDER_TIME_GTC;   // expiry handled by ManagePendingOrders (broker-agnostic)
    request.comment = "NyaoLE|" + DoubleToString(signalScore, 2); // stash entry-thesis score
    request.price = entry;

    double slPts = GetSLPoints(currentLot);
    double tpPts = GetTPPoints(currentLot);
    if(dir == ORDER_TYPE_BUY)
    {
        request.type = ORDER_TYPE_BUY_LIMIT;
        if(slPts > 0)
            request.sl = NormalizeDouble(entry - slPts * _Point, _Digits);
        if(tpPts > 0)
            request.tp = NormalizeDouble(entry + tpPts * _Point, _Digits);
    }
    else
    {
        request.type = ORDER_TYPE_SELL_LIMIT;
        if(slPts > 0)
            request.sl = NormalizeDouble(entry + slPts * _Point, _Digits);
        if(tpPts > 0)
            request.tp = NormalizeDouble(entry - tpPts * _Point, _Digits);
    }

    AtlasBeginOrderAttempt(dir, "LIMIT");
    bool atlasLimitSendOk = OrderSend(request, result);
    atlasLastOrderRetcode = (long)result.retcode;

    if(atlasLimitSendOk && result.retcode == TRADE_RETCODE_DONE)
    {
        atlasLastOrderSuccess = true;
        atlasLastOrderTicket = result.order;
        AtlasSetDecisionReason(atlasDir, "LIMIT_ORDER_PLACED", true);
        double depthPts = MathAbs(ref - entry) / _Point;
        LogPrint("+-----------------------------------------+");
        LogPrint("[LIMIT ENTRY PLACED] ", dir == ORDER_TYPE_BUY ? "BUY LIMIT" : "SELL LIMIT",
                 " | Anchor: ", EnumToString(LimitEntryAnchor));
        LogPrint("Price: ", entry, " | Depth: ", DoubleToString(depthPts, 0),
                 " pts (cap ", DoubleToString(LimitEntryATRFraction, 2), " ATR)");
        LogPrint("Lot: ", currentLot, " | Signal: ", DoubleToString(signalScore, 1));
        LogPrint("+-----------------------------------------+");
    }
    else
    {
        AtlasSetDecisionReason(atlasDir, atlasLimitSendOk ? "LIMIT_ORDER_REJECTED" : "LIMIT_ORDER_SEND_ERROR");
        LogPrint("[LIMIT ENTRY] OrderSend failed. Retcode: ", result.retcode, " Error: ", GetLastError());
    }

    LockOrderSend(false);
}

// Count our working (pending) limit orders on this symbol
int CountWorkingLimitOrders()
{
    int count = 0;
    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        ulong ticket = OrderGetTicket(i);
        if(ticket == 0) continue;
        if(!OrderSelect(ticket)) continue;
        if(OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;
        if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
        ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
        if(ot == ORDER_TYPE_BUY_LIMIT || ot == ORDER_TYPE_SELL_LIMIT) count++;
    }
    return count;
}

// Cancel a pending order
bool DeletePendingOrder(ulong ticket)
{
    LockOrderSend(true);
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    request.action = TRADE_ACTION_REMOVE;
    request.order = ticket;
    bool ok = OrderSend(request, result);
    if(!ok || result.retcode != TRADE_RETCODE_DONE)
        LogPrint("[LIMIT ENTRY] Cancel failed for ", ticket, " Retcode: ", result.retcode, " Error: ", GetLastError());
    LockOrderSend(false);
    return (ok && result.retcode == TRADE_RETCODE_DONE);
}

// Recover the stashed entry-thesis score from a limit-order comment (-1 if absent)
double ParseLimitEntryScore(string comment)
{
    int p = StringFind(comment, "NyaoLE|");
    if(p < 0) return -1;
    return StringToDouble(StringSubstr(comment, p + 7));
}

// +------------------------------------------------------------------+
// | Manage Pending Limit Entries                                     |
// | Cancels unfilled pendings on expiry (bar age) or when the         |
// | directional signal no longer clears its threshold. Runs in every  |
// | state (called from ManagePositions) so stale pendings can't fill. |
// +------------------------------------------------------------------+
void ManagePendingOrders()
{
    if(!EnableLimitEntry) return;

    for(int i = OrdersTotal() - 1; i >= 0; i--)
    {
        ulong ticket = OrderGetTicket(i);
        if(ticket == 0) continue;
        if(!OrderSelect(ticket)) continue;
        if(OrderGetInteger(ORDER_MAGIC) != MagicNumber) continue;
        if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;

        ENUM_ORDER_TYPE ot = (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE);
        if(ot != ORDER_TYPE_BUY_LIMIT && ot != ORDER_TYPE_SELL_LIMIT) continue;

        // 1. Expiry by bar age (broker-agnostic; placed GTC and aged out here)
        if(LimitEntryExpiryBars > 0)
        {
            datetime setup = (datetime)OrderGetInteger(ORDER_TIME_SETUP);
            int barsElapsed = iBarShift(_Symbol, _Period, setup, false);
            if(barsElapsed >= LimitEntryExpiryBars)
            {
                LogPrint("[LIMIT ENTRY] Expired after ", barsElapsed, " bar(s). Cancelling ticket ", ticket);
                DeletePendingOrder(ticket);
                continue;
            }
        }

        // 2. Cancel when the directional signal no longer clears its threshold
        if(LimitEntryCancelOnFlip)
        {
            bool buy = (ot == ORDER_TYPE_BUY_LIMIT);
            SignalStrength s = GetSignalStrength(buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
            double thr = buy ? atlasRuntime.minBuySignalScore : atlasRuntime.minSellSignalScore;
            if(s.finalScore < thr)
            {
                LogPrint("[LIMIT ENTRY] Signal faded (", DoubleToString(s.finalScore, 1),
                         " < ", DoubleToString(thr, 1), "). Cancelling ticket ", ticket);
                DeletePendingOrder(ticket);
            }
        }
    }
}

// Close Position
bool ClosePosition(ulong ticket)
{
    if(!PositionSelectByTicket(ticket))
    {
        LogPrint("Position ", ticket, " not found");
        return false;
    }

    LockOrderSend(true);
    
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_DEAL;
    request.position = ticket;
    request.symbol = PositionGetString(POSITION_SYMBOL);
    request.volume = PositionGetDouble(POSITION_VOLUME);
    request.deviation = 10;
    request.magic = PositionGetInteger(POSITION_MAGIC);
    request.type_filling = GetFillingMode();

    ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
    request.type = (type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
    request.price = (type == POSITION_TYPE_BUY) ?
                    SymbolInfoDouble(_Symbol, SYMBOL_BID) :
                    SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    
    if(!OrderSend(request, result))
    {
        LogPrint("Failed to close position ", ticket, " Error: ", GetLastError());
        LockOrderSend(false);
        return false;
    }
    
    LogPrint("Position ", ticket, " closed successfully");
    LockOrderSend(false);
    return true;
}

// Close all positions regardless of profit/loss
void CloseAllPositions(bool unProfitableOnly = false, bool skipChainLegs = false)
{
    int closedCount = 0;

    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);

        if(PositionSelectByTicket(ticket))
        {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
               PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                double profit = PositionGetDouble(POSITION_PROFIT);

                if (unProfitableOnly && profit >= 0) continue;

                // Leave active hedge-chain legs alone (basket stop only sweeps normal trades)
                if(skipChainLegs && atlasRuntime.enableHedgeChain)
                {
                    int idx = GetManagedPositionIndex(ticket);
                    if(idx != -1 && managedPositions[idx].chainId != 0) continue;
                }

                LogPrint("Closing position. Ticket: ", ticket, ", Profit/Loss: $", profit);

                if(ClosePosition(ticket))
                {
                    closedCount++;
                    LogPrint("Position closed successfully: ", ticket);
                }
                else
                {
                    LogPrint("ERROR: Failed to close position: ", ticket, ". Error: ", GetLastError());
                }
            }
        }
    }
    
    if(closedCount > 0)
    {
        LogPrint("Total positions closed: ", closedCount);
    }
}

// Modify position SL/TP
bool ModifyPosition(ulong ticket, double newSL, double newTP)
{
    // Select the position
    if(!PositionSelectByTicket(ticket))
    {
        LogPrint("Error: Failed to select position #", ticket);
        return false;
    }
    
    // Get position information
    string symbol = PositionGetString(POSITION_SYMBOL);
    double currentSL = PositionGetDouble(POSITION_SL);
    double currentTP = PositionGetDouble(POSITION_TP);
    
    // Prepare request
    MqlTradeRequest request = {};
    MqlTradeResult result = {};
    
    request.action = TRADE_ACTION_SLTP;
    request.position = ticket;
    request.symbol = symbol;
    request.sl = NormalizeDouble(newSL, _Digits);
    request.tp = NormalizeDouble(newTP, _Digits);

    // Prevent unnecessary modifications
    if(NormalizeDouble(newSL, _Digits) == NormalizeDouble(currentSL, _Digits) && 
       NormalizeDouble(newTP, _Digits) == NormalizeDouble(currentTP, _Digits))
    {
        return true;
    }
    
    // Send modification request
    if(!OrderSend(request, result))
    {
        LogPrint("PositionModify failed for position #", ticket, " Error: ", GetLastError());
        LogPrint("Retcode: ", result.retcode, " - ", result.comment);
        return false;
    }
    
    LogPrint("Position #", ticket, " modified successfully");
    LogPrint("Old SL: ", currentSL, " -> New SL: ", newSL);
    LogPrint("Old TP: ", currentTP, " -> New TP: ", newTP);
    
    return true;
}

// Helper function to check is allowed to open position
bool IsAllowedToOpenPosition()
{
    atlasLastGlobalBlockReason = "NONE";

    if(!atlasEnabled)
    {
        atlasLastGlobalBlockReason = "ATLAS_DISABLED";
        return false;
    }
    if (targetEquityReached || minimumEquityReached || minEquityTriggersExceeded)
    {
        atlasLastGlobalBlockReason = "EQUITY_GUARD";
        LogPrint("+-----------------------------------------+");
        LogPrint("OPEN ORDER BLOCKED!");
        LogPrint("Trading Stopped! Opening new order are not allowed!");
        LogPrint("+-----------------------------------------+");
        return false;
    }

    if (isPaused || isOutsideTradingHours || isLeverageDiffFromInitial)
    {
        atlasLastGlobalBlockReason = isPaused ? "TRADING_PAUSED" : (isOutsideTradingHours ? "OUTSIDE_TRADING_HOURS" : "LEVERAGE_CHANGED");
        LogPrint("+-----------------------------------------+");
        LogPrint("OPEN ORDER BLOCKED!");
        LogPrint("Trading Paused! Opening new order are not allowed during pause period!");
        LogPrint("+-----------------------------------------+");
        return false;
    }
    
    if(isNearMarketClose)
    {
        atlasLastGlobalBlockReason = "MARKET_CLOSE_FILTER";
        LogPrint("+-----------------------------------------+");
        LogPrint("OPEN ORDER BLOCKED!");
        LogPrint("Market closing soon! No opening new positions.");
        LogPrint("+-----------------------------------------+");
        return false;
    }

    if (CountLosingPositions() >= MaxHoldingLossPositions)
    {
        atlasLastGlobalBlockReason = "MAX_HOLDING_LOSS_POSITIONS";
        LogPrint("+-----------------------------------------+");
        LogPrint("OPEN ORDER BLOCKED!");
        LogPrint("Maximum holding loss positions reached!");
        LogPrint("+-----------------------------------------+");
        return false;
    }

    if (CountOpenOrders() >= atlasRuntime.maxOpenOrders)
    {
        atlasLastGlobalBlockReason = "MAX_OPEN_ORDERS";
        LogPrint("+-----------------------------------------+");
        LogPrint("OPEN ORDER BLOCKED!");
        LogPrint("Maximum consecutive open order reached!");
        LogPrint("+-----------------------------------------+");
        return false;
    }

    if (isOrderSendLocked) {
        atlasLastGlobalBlockReason = "ORDER_SEND_LOCKED";
        LogPrint("+-----------------------------------------+");
        LogPrint("OPEN ORDER BLOCKED!");
        LogPrint("An order is still being processed!");
        LogPrint("+-----------------------------------------+");
        return false;
    }

    if (IsSpreadTooWide())
    {
        atlasLastGlobalBlockReason = "SPREAD_TOO_WIDE";
        LogPrint("+-----------------------------------------+");
        LogPrint("OPEN ORDER BLOCKED!");
        LogPrint("Spread too wide for entry.");
        LogPrint("+-----------------------------------------+");
        return false;
    }

    return true;
}

// +------------------------------------------------------------------+
// | Spread Filter - Block entries when spread is too wide            |
// | When MaxSpreadPoints > 0 uses a fixed cap, otherwise derives a   |
// | cap from current ATR (MaxSpreadATRRatio fraction of ATR points)  |
// +------------------------------------------------------------------+
bool IsSpreadTooWide()
{
    if(!EnableMaxSpreadFilter) return false;

    double spreadPoints = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);

    double cap = MaxSpreadPoints;
    if(cap <= 0)
    {
        // Auto mode: cap = fraction of current ATR expressed in points
        double bufATR[];
        ArraySetAsSeries(bufATR, true);
        if(CopyBuffer(atrSignalHandle, 0, 0, 1, bufATR) < 1) return false; // can't judge, don't block
        double atrPoints = (_Point > 0) ? bufATR[0] / _Point : 0;
        cap = atrPoints * MaxSpreadATRRatio;
        if(cap <= 0) return false; // no usable ATR, don't block
    }

    if(spreadPoints > cap)
    {
        LogPrint("[SPREAD] Blocked: spread ", DoubleToString(spreadPoints, 0),
                 " pts > cap ", DoubleToString(cap, 0), " pts");
        return true;
    }

    return false;
}


// Helper function to lock/unlock OrderSend execution
void LockOrderSend(bool isLocked)
{
    isOrderSendLocked = isLocked;
}

// Helper function to get the supported filling mode for the current symbol
ENUM_ORDER_TYPE_FILLING GetFillingMode()
{
    uint filling = (uint)SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
    if((filling & SYMBOL_FILLING_FOK) != 0) return ORDER_FILLING_FOK;
    if((filling & SYMBOL_FILLING_IOC) != 0) return ORDER_FILLING_IOC;
    return ORDER_FILLING_RETURN;
}

// Helper function to validate SL price
bool IsSLValid(ENUM_POSITION_TYPE posType, double sl)
{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);

    long stopLevel   = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
    long freezeLevel = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);

    double minDistance = MathMax(stopLevel, freezeLevel) * _Point;

    if(posType == POSITION_TYPE_BUY)
    {
        if(sl >= bid - minDistance) return false;
    }
    else
    {
        if(sl <= ask + minDistance) return false;
    }

    return true;
}

// Helper for normalize volume
double NormalizeVolume(double volume)
{
    double minVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double stepVol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    
    volume = MathMax(volume, minVol);
    volume = MathMin(volume, maxVol);
    volume = MathRound(volume / stepVol) * stepVol;
    
    return volume;
}

// Helper to count open orders
int CountOpenOrders()
{
    int count = 0;
    
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);

        if(PositionSelectByTicket(ticket))
        {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
               PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                count++;
            }
        }
    }
    
    return count;
}

int CountOpenOrdersByType(ENUM_POSITION_TYPE posType)
{
    int count = 0;
    
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);

        if(PositionSelectByTicket(ticket))
        {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
               PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
               PositionGetInteger(POSITION_TYPE) == posType)
            {
                count++;
            }
        }
    }
    
    return count;
}
// +------------------------------------------------------------------+

//+-------------------------------------------------------------------+
//| Calculate Dynamic Lot Size - Equity Drop Recovery Based           |
//| Lot increases based on equity drop from peak to recover losses    |
//| Only applies when signal score meets MinSignalStrengthForLot      |
//+-------------------------------------------------------------------+
double CalculateDynamicLotSize(double signalScore = 0)
{
    if(!atlasRuntime.enableDynamicLots) return atlasRuntime.baseLotSize;
    
    double currentLot = atlasRuntime.baseLotSize;
    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    
    // Calculate equity drop from peak as percentage
    double equityDropPercent = 0;
    if(peakEquity > 0)
    {
        equityDropPercent = ((peakEquity - currentEquity) / peakEquity) * 100.0;
    }
    
    // Each EquityDropPercent step adds LotStepSize
    // Only increase lot if signal score validates the entry
    // GUARDRAILS: never scale up while already bleeding (cooldown after losses
    // or an active basket loss), and cap the number of drawdown-based steps.
    bool inCooldown = (cooldownUntilBarTime > 0 && iTime(_Symbol, _Period, 0) < cooldownUntilBarTime);
    bool basketBleeding = (EnableBasketStop && GetTotalFloatingPL() < 0);

    int equitySteps = 0;
    if(equityDropPercent > 0 && EquityDropPercent > 0 && signalScore >= MinSignalStrengthForLot
       && !inCooldown && !basketBleeding)
    {
        equitySteps = (int)(equityDropPercent / EquityDropPercent);

        // Cap cumulative drawdown lot steps (0 = unlimited)
        if(MaxEquityDropLotSteps > 0 && equitySteps > MaxEquityDropLotSteps)
            equitySteps = MaxEquityDropLotSteps;
    }

    double equityLotIncrease = equitySteps * LotStepSize;
    currentLot += equityLotIncrease;
    
    // APPLY LIMITS
    // Apply user-defined limits
    if(currentLot < atlasRuntime.baseLotSize) currentLot = atlasRuntime.baseLotSize;
    if(currentLot > MaxLotSize) currentLot = MaxLotSize;
    
    // Round to 2 decimal places (standard lot step)
    currentLot = NormalizeDouble(currentLot, 2);
    
    // Apply broker limits
    double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);

    if(currentLot < minLot) currentLot = minLot;
    if(currentLot > maxLot) currentLot = maxLot;
        
    // Round to valid lot step
    currentLot = MathFloor(currentLot / lotStep) * lotStep;
    
    // MARGIN CHECK
    double marginNeeded = 0;

    if(!OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, currentLot, SymbolInfoDouble(_Symbol, SYMBOL_ASK), marginNeeded))
    {
        LogPrint("ERROR: Failed to calculate margin: ", GetLastError());
        return minLot;
    }

    double availableMargin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);

    if(marginNeeded > availableMargin)
    {
        double symbolLotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
        double maxAffordableLot = minLot;
        double testMargin = 0;  
        
        if (symbolLotStep == 0) symbolLotStep = 0.01;
        
        double testLot = minLot;
        
        while(testLot <= currentLot)
        {   
            if(OrderCalcMargin(ORDER_TYPE_BUY, _Symbol, testLot, SymbolInfoDouble(_Symbol, SYMBOL_ASK), testMargin))
            {
                if(testMargin <= availableMargin)
                {
                    maxAffordableLot = testLot;
                    testLot += symbolLotStep;
                }
                else
                {
                    break;
                }
            }
            else
            {
                break;
            }
        }
        
        currentLot = maxAffordableLot;
        
        if(currentLot < minLot)
        {
            LogPrint("WARNING: Insufficient margin. Required: $", marginNeeded, 
                  ", Available: $", availableMargin);
            return minLot;
        }
        
        LogPrint("WARNING: Reduced lot from calculated to affordable: ", currentLot, 
              " (Required margin: $", marginNeeded, ", Available: $", availableMargin, ")");
    }
    
    LogPrint("Dynamic Lot Calculation: Base=", atlasRuntime.baseLotSize, 
             " | Equity Drop Steps=", equitySteps, " (+", equityLotIncrease, ")",
             " | Signal Steps=", (signalScore >= MinSignalStrengthForLot ? (signalScore - MinSignalStrengthForLot) / 2 : 0),
             " | Final Lot=", currentLot);
    
    return currentLot;
}

// +------------------------------------------------------------------+
// | Calculate True Break-even Price                                  |
// +------------------------------------------------------------------+
double CalculateBreakEvenPrice(ulong ticket, ENUM_POSITION_TYPE posType, double entryPrice, double volume)
{
    // Get current spread
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double spread = ask - bid;
    
    // Get commission using deals 
    double commission = GetPositionRoundTripCommission(ticket);
    
    // Get swap
    double swap = 0;
    if(PositionSelectByTicket(ticket))
    {
        swap = PositionGetDouble(POSITION_SWAP);
    }
    
    // For total cost, only count swap if it's negative (a cost)
    double swapCost = (swap < 0) ? MathAbs(swap) : 0;

    // Calculate total cost in account currency
    double totalCost = commission + swapCost;
    
    // Convert cost to price distance
    double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    
    double costInPrice = 0;
    double minProfitInPrice = 0;

    if(tickValue != 0 && volume != 0)
    {   
        // Convert cost to price
        costInPrice = (totalCost / volume) * (tickSize / tickValue);

        // Convert MinBreakEvenProfit ($) to price (0 = disabled, no offset)
        if(MinBreakEvenProfit > 0)
            minProfitInPrice = (MinBreakEvenProfit / volume) * (tickSize / tickValue);
    }
    
    // Calculate break-even price
    double breakEvenPrice;
    if(posType == POSITION_TYPE_BUY)
    {
        // BUY: Entry + spread + costs
        breakEvenPrice = entryPrice + spread + costInPrice + minProfitInPrice;
    }
    else
    {
        // SELL: Entry - spread - costs
        breakEvenPrice = entryPrice - spread - costInPrice - minProfitInPrice;
    }
    
    return NormalizeDouble(breakEvenPrice, _Digits);
}

// Get Total Commission for a position (entry + exit estimate)
double GetPositionRoundTripCommission(ulong positionTicket)
{
    double entryCommission = 0.0;
    
    if(!HistorySelectByPosition(positionTicket)) return 0.0;
    
    // Get entry commission
    for(int i = 0; i < HistoryDealsTotal(); i++)
    {
        ulong dealTicket = HistoryDealGetTicket(i);
        
        if(dealTicket > 0)
        {
            ENUM_DEAL_ENTRY dealEntry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(dealTicket, DEAL_ENTRY);
            
            if(dealEntry == DEAL_ENTRY_IN)
            {
                entryCommission += HistoryDealGetDouble(dealTicket, DEAL_COMMISSION);
                break; // Found entry, no need to continue
            }
        }
    }
    
    // Double it to estimate round-trip (entry + exit)
    // This is an approximation since exit commission hasn't happened yet
    return MathAbs(entryCommission) * 2.0;
}
// +------------------------------------------------------------------+

// +------------------------------------------------------------------+
// | Convert Input Value to Points Based on Input Type                |
// +------------------------------------------------------------------+
double ConvertToPoints(ENUM_INPUT_TYPE inputType, double value, double lotSize)
{
    double points = 0;
    
    switch(inputType)
    {
        case INPUT_POINTS:
            points = value;
            break;
            
        case INPUT_DOLLAR:
            {
                double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
                double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
                double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
                
                if(tickValue > 0 && tickSize > 0 && lotSize > 0 && point > 0)
                {
                    // Normalize tick value to the lot size we're using
                    double normalizedTickValue = tickValue * lotSize;
                    
                    // Calculate how many points in one tick
                    double pointsPerTick = tickSize / point;

                    if(pointsPerTick <= 0)
                    {
                        LogPrint("Error: Invalid pointsPerTick (", pointsPerTick, ")");
                        return 0;
                    }

                    // Value per point = (value per tick) / (points per tick)
                    double valuePerPoint = normalizedTickValue / pointsPerTick;
                    
                    // Convert dollars to points
                    points = value / valuePerPoint;
                }
                else
                {
                    LogPrint("Error: Invalid tick value (", tickValue, "), tick size (", tickSize, "), point (", point, "), or lot size (", lotSize, ")");
                }
            }
            break;
            
        case INPUT_PERCENT:
            {
                double equity = AccountInfoDouble(ACCOUNT_EQUITY);  
                double dollarAmount = equity * (value / 100.0);
                
                // Reuse the dollar conversion logic
                double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
                double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
                double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
                
                if(tickValue > 0 && tickSize > 0 && lotSize > 0 && point > 0)
                {   
                    // Normalize tick value to the lot size we're using
                    double normalizedTickValue = tickValue * lotSize;

                    // Calculate how many points in one tick
                    double pointsPerTick = tickSize / point;

                    if(pointsPerTick <= 0)
                    {
                        LogPrint("Error: Invalid pointsPerTick in percent conversion (", pointsPerTick, ")");
                        return 0;
                    }
                    
                    // Value per point = (value per tick) / (points per tick)
                    double valuePerPoint = normalizedTickValue / pointsPerTick;

                    // Convert dollars to points
                    points = dollarAmount / valuePerPoint;
                }
                else
                {
                    LogPrint("Error: Invalid parameters for percent conversion");
                }
            }
            break;
    }
    
    return points;
}

// +------------------------------------------------------------------+
// | Current ATR value in price terms (last closed bar, 0 on failure). |
// +------------------------------------------------------------------+
double GetCurrentATR()
{
    double buf[];
    ArraySetAsSeries(buf, true);
    if(CopyBuffer(atrSignalHandle, 0, 1, 1, buf) < 1) return 0;
    return buf[0];
}

// +------------------------------------------------------------------+
// | Risk:Reward risk (SL) leg in points - independent of manual SL.   |
// | Manual mode: own input (points/dollar/percent).                   |
// | ATR mode: SL = ATR × multiplier, auto-calculated on entry.        |
// +------------------------------------------------------------------+
double GetRRRiskPoints(double lotSize)
{
    if(RRRiskMode == RR_RISK_ATR)
    {
        double atr = GetCurrentATR();
        if(atr <= 0 || _Point <= 0) return 0;
        double atrPoints = atr / _Point;
        return atrPoints * RRAtrMultiplier;
    }

    // Manual distance
    return ConvertToPoints(RRRiskInputType, RRRiskValue, lotSize);
}

// +------------------------------------------------------------------+
// | Resolve SL distance in points for a given lot (0 = no SL).        |
// | Independent R:R mode overrides the manual Stop Loss entirely.     |
// +------------------------------------------------------------------+
double GetSLPoints(double lotSize)
{
    if(EnableRiskReward)
        return GetRRRiskPoints(lotSize);

    if(EnableStopLoss)
        return ConvertToPoints(SLInputType, SLValue, lotSize);

    return 0;
}

// +------------------------------------------------------------------+
// | Resolve TP distance in points for a given lot (0 = no TP).        |
// | Independent R:R mode sets TP = risk distance × ratio, overriding  |
// | the manual Take Profit entirely.                                  |
// +------------------------------------------------------------------+
double GetTPPoints(double lotSize)
{
    if(EnableRiskReward)
    {
        double slPts = GetRRRiskPoints(lotSize);
        if(slPts > 0 && RiskRewardRatio > 0)
            return slPts * RiskRewardRatio;
        return 0;
    }

    if(EnableTakeProfit)
        return ConvertToPoints(TPInputType, TPValue, lotSize);

    return 0;
}

// +------------------------------------------------------------------+
// | Monitor High-Impact News Events & Return Event Details           |
// +------------------------------------------------------------------+
string IsHighImpactNewsTime(int minutesBefore, int minutesAfter, ulong &eventID)
{
    MqlCalendarValue values[];
    
    datetime serverTime = TimeTradeServer();
    // Use the max of both windows to cover all events in their active pause window
    // Add 120s buffer to avoid boundary exclusion issues in CalendarValueHistory
    int lookRange = (int)MathMax(minutesBefore, minutesAfter);
    datetime start = serverTime - lookRange * 60;
    datetime end = serverTime + lookRange * 60 + 120;
    
    if(CalendarValueHistory(values, start, end))
    {
        for(int i = 0; i < ArraySize(values); i++)
        {
            MqlCalendarEvent event;
            if(CalendarEventById(values[i].event_id, event))
            {
                if(event.importance == CALENDAR_IMPORTANCE_HIGH)
                {
                    // Get country info
                    MqlCalendarCountry country;
                    CalendarCountryById(event.country_id, country);
                    
                    // Check if event currency matches symbol currencies
                    if(country.currency != symbolBaseCurrency && 
                       country.currency != symbolQuoteCurrency)
                    {
                        continue;
                    }
                    
                    // Check if we're within the event window (before OR after)
                    datetime eventTime = values[i].time;
                    datetime pauseStart = eventTime - minutesBefore * 60;
                    datetime pauseEnd = eventTime + minutesAfter * 60;
                    
                    if(serverTime < pauseStart || serverTime > pauseEnd)
                    {
                        continue;
                    }
                    
                    eventID = values[i].event_id;
                    
                    int secondsUntil = (int)(eventTime - serverTime);
                    int minutesUntil = secondsUntil / 60;
                    
                    string eventDetails = "";
                    eventDetails += "**Event Name:** " + event.name + "\n";
                    eventDetails += "**Country:** " + country.name + " (" + country.code + ")\n";
                    eventDetails += "**Currency:** " + country.currency + "\n";
                    eventDetails += "**Event Time:** " + TimeToString(eventTime, TIME_DATE|TIME_SECONDS) + "\n";
                    eventDetails += "**Time Until:** " + IntegerToString(minutesUntil) + " minutes\n";
                    
                    if(values[i].HasActualValue())
                        eventDetails += "**Actual:** " + DoubleToString(values[i].GetActualValue(), 2) + "\n";
                    if(values[i].HasForecastValue())
                        eventDetails += "**Forecast:** " + DoubleToString(values[i].GetForecastValue(), 2) + "\n";
                    if(values[i].HasPreviousValue())
                        eventDetails += "**Previous:** " + DoubleToString(values[i].GetPreviousValue(), 2) + "\n";
                    
                    eventDetails += "**Importance:** " + EnumToString(event.importance) + "\n";
                    eventDetails += "**Pause Window:** " + TimeToString(pauseStart, TIME_SECONDS) + 
                                   " to " + TimeToString(pauseEnd, TIME_SECONDS);
                    
                    LogPrint("High impact event for ", country.currency, ": ", event.name);
                    
                    return eventDetails;
                }
            }
        }
    }
    
    eventID = 0;
    return "";
}

// +------------------------------------------------------------------+
// | Check If Current Time is Within Allowed Trading Hours            |
// +------------------------------------------------------------------+
bool IsWithinTradingHours()
{   
    // Always allow trading if feature is disabled
    if(!EnableTradingHours) return true;
    
    // Get current server time
    datetime currentTime = TimeTradeServer();
    MqlDateTime timeStruct;
    TimeToStruct(currentTime, timeStruct);
    
    // Current time in minutes from midnight
    int currentMinutes = timeStruct.hour * 60 + timeStruct.min;
    
    // Parse start time
    string startParts[];

    int startCount = StringSplit(TradingStartTime, ':', startParts);
    if(startCount != 2)
    {
        LogPrint("ERROR: Invalid TradingStartTime format. Use HH:MM");
        return false;
    }

    int startHour = (int)StringToInteger(startParts[0]);
    int startMin = (int)StringToInteger(startParts[1]);
    int startMinutes = startHour * 60 + startMin;
    
    // Parse end time
    string endParts[];

    int endCount = StringSplit(TradingEndTime, ':', endParts);
    if(endCount != 2)
    {
        LogPrint("ERROR: Invalid TradingEndTime format. Use HH:MM");
        return false;
    }

    int endHour = (int)StringToInteger(endParts[0]);
    int endMin = (int)StringToInteger(endParts[1]);
    int endMinutes = endHour * 60 + endMin;
    
    // Handle overnight trading sessions (e.g., 22:00 to 02:00)
    if(startMinutes > endMinutes)
    {
        // Trading period crosses midnight
        return (currentMinutes >= startMinutes || currentMinutes <= endMinutes);
    }
    else
    {
        // Normal trading period within same day
        return (currentMinutes >= startMinutes && currentMinutes <= endMinutes);
    }
}

// +------------------------------------------------------------------+
// | Check and Update Peak Equity                                     |
// +------------------------------------------------------------------+
void CheckPeakEquity()
{
    // Get current equity
    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    
    // Update peak equity if current is higher
    if(currentEquity > peakEquity)
    {
        peakEquity = currentEquity;
        lastPeakEquity = currentEquity;
        
        // Reset min equity triggers on new peak
        if (ResetOnNewPeak) minEquityTriggerCount = 0; 
        
        LogPrint("New Peak Equity reached: $", peakEquity);
        
        // Reset pause if equity recovered above peak
        if(isPaused)
        {
            isPaused = false;
            LogPrint("Trading RESUMED - Equity recovered above peak!");
        }
    }
}

// +------------------------------------------------------------------+
// | Check Target Equity                                              |
// +------------------------------------------------------------------+
void CheckTargetEquity()
{   
    // Get current equity
    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);

    if(TargetEquity > 0 && !targetEquityReached && currentEquity >= TargetEquity)
    {
        targetEquityReached = true;
        
        LogPrint("+-----------------------------------------+");
        LogPrint("TARGET EQUITY REACHED!");
        LogPrint("Current Equity: $", currentEquity);
        LogPrint("Target Equity: $", TargetEquity);
        LogPrint("Closing ALL positions and stopping trading...");
        LogPrint("+-----------------------------------------+");
        
        // Send Discord alert for target equity reached
        if(EnableDiscordAlerts)
        {
            string alertMsg = "**Instrument:** " + _Symbol + "\n";
            alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
            alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
            alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
            alertMsg += "**Target Equity:** $" + DoubleToString(TargetEquity, 2) + "\n";
            alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
            alertMsg += "**Profit:** $" + DoubleToString(TargetEquity - initialBalance, 2) + "\n";
            alertMsg += "**Action:** All Positions Closed, Trading Stopped!";
            
            SendDiscordAlert("🎯 TARGET EQUITY REACHED!", alertMsg, 5763719); // Green color
        }
        
        Alert("TARGET EQUITY REACHED! Closing all positions and stopping trading.");
    }
}

// +------------------------------------------------------------------+
// | Check minimum Tradeable Equity                                   |
// +------------------------------------------------------------------+
void CheckMinTradeableEquity() 
{   
    // Get current equity
    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);

    if(MinimumEquity > 0 && !minimumEquityReached && currentEquity <= MinimumEquity)
    {
        minimumEquityReached = true;
        LogPrint("+-----------------------------------------+");
        LogPrint("MINIMUM TRADEABLE EQUITY REACHED!");
        LogPrint("Current Equity: $", currentEquity);
        LogPrint("Minimum Equity: $", MinimumEquity);
        LogPrint("Closing ALL positions and stopping trading...");
        LogPrint("+-----------------------------------------+");
        
        // Send Discord alert for minimum equity reached
        if(EnableDiscordAlerts)
        {   
            string alertMsg = "**Instrument:** " + _Symbol + "\n";
            alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
            alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
            alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
            alertMsg += "**Minimum Equity:** $" + DoubleToString(MinimumEquity, 2) + "\n";
            alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
            alertMsg += "**Loss:** $" + DoubleToString(initialBalance - currentEquity, 2) + "\n";
            alertMsg += "**Action:** All Positions Closed, Trading Stopped!";
            
            SendDiscordAlert("🔴 MINIMUM TRADEABLE EQUITY REACHED", alertMsg, 15158332); // Red color
        }
        
        Alert("MINIMUM TRADEABLE EQUITY REACHED! Closing all positions and stopping trading.");
    }
}

// +------------------------------------------------------------------+
// | Check Equity Drawdawn                                            |
// +------------------------------------------------------------------+
void CheckEquityDrawdawn()
{   
    // Get current equity
    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);

    // Calculate allowed drawdown
    double drawdownFromPercent = lastPeakEquity * ((100.0 - MinEquityPercent) / 100.0);
    
    // If MaxDrawdownFromPeak is 0 or negative, don't cap it
    double allowedDrawdown = (MaxDrawdownFromPeak > 0) ? 
    MathMin(drawdownFromPercent, MaxDrawdownFromPeak)
    : drawdownFromPercent;
    
    double minAllowedEquity = lastPeakEquity - allowedDrawdown;
    
    // Check equity condition and handle pause
    if(currentEquity < minAllowedEquity)
    {
        if(!isPaused)
        {
            // Increment trigger counter
            minEquityTriggerCount++;
            
            // Check if max triggers exceeded
            if(MaxMinEquityTriggers > 0 && minEquityTriggerCount > MaxMinEquityTriggers)
            {
                minEquityTriggersExceeded = true;
                LogPrint("+-----------------------------------------+" );
                LogPrint("MAX MIN EQUITY TRIGGERS EXCEEDED!");
                LogPrint("Triggers Used: ", minEquityTriggerCount, " / ", MaxMinEquityTriggers);
                LogPrint("Closing ALL positions and STOPPING TRADING...");
                LogPrint("+-----------------------------------------+" );
                
                if(EnableDiscordAlerts)
                {   
                    string alertMsg = "**Instrument:** " + _Symbol + "\n";
                    alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
                    alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
                    alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
                    alertMsg += "**Peak Equity:** $" + DoubleToString(lastPeakEquity, 2) + "\n";
                    alertMsg += "**Triggers Used:** " + IntegerToString(minEquityTriggerCount) + " / " + IntegerToString(MaxMinEquityTriggers) + "\n";
                    alertMsg += "**Action:** All Positions Closed, Trading Stopped!";
                    
                    SendDiscordAlert("🔴 MAX MIN EQUITY TRIGGERS EXCEEDED", alertMsg, 15158332); // Red color
                }
                
                Alert("MAX MIN EQUITY TRIGGERS EXCEEDED! Closing all positions and stopping trading.");
                return;
            }
            
            // First time hitting minimum equity
            isPaused = true;
            pauseStartTime = TimeTradeServer();
            
            // Use the trigger count to calculate exponential pause duration
            double calculatedDuration = PauseMinutes * MathPow(PauseMinutesMultiplier, minEquityTriggerCount - 1);
            if(calculatedDuration > INT_MAX) calculatedDuration = INT_MAX;
            currentPauseDuration = (int)MathMin(calculatedDuration, MaxPauseMinutes > 0 ? MaxPauseMinutes : INT_MAX);
            
            // Update Pause Stats
            totalPauseCount++;
            totalPauseDurationMinutes += currentPauseDuration;
            
            // Calculate drop peek equity
            double equityDrop = lastPeakEquity - currentEquity;
            double equityDropPercent = (equityDrop / lastPeakEquity) * 100.0;
            
            // Store old peak for Discord alert
            double oldPeakEquity = lastPeakEquity;
            
            // Update peak equity to current balance
            lastPeakEquity = AccountInfoDouble(ACCOUNT_BALANCE);
            
            LogPrint("+-----------------------------------------+");
            LogPrint("EQUITY PROTECTION TRIGGERED!");
            LogPrint("Current Equity: $", currentEquity);
            LogPrint("Peak Equity: $", peakEquity);
            LogPrint("Old Peak Equity: $", oldPeakEquity);
            LogPrint("New Peak Equity (Balance): $", lastPeakEquity);
            LogPrint("Min Allowed (", MinEquityPercent, "%): $", minAllowedEquity);
            LogPrint("Trading PAUSED for ", currentPauseDuration, " minutes");
            LogPrint("Resume Time: ", TimeToString(pauseStartTime + currentPauseDuration * 60));
            LogPrint("+-----------------------------------------+");
            
            // Send Discord alert for minimum equity reached
            if(EnableDiscordAlerts)
            {   
                string alertMsg = "**Instrument:** " + _Symbol + "\n";
                alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
                alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
                alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
                alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
                alertMsg += "**Previous Peak:** $" + DoubleToString(oldPeakEquity, 2) + "\n";
                alertMsg += "**New Peak (Balance):** $" + DoubleToString(lastPeakEquity, 2) + "\n";
                alertMsg += "**Equity Drop:** $" + DoubleToString(equityDrop, 2) + " (" + DoubleToString(equityDropPercent, 2) + "%)\n";
                alertMsg += "**Min Allowed (" + DoubleToString(MinEquityPercent, 0) + "%):** $" + DoubleToString(minAllowedEquity, 2) + "\n";
                alertMsg += "**Trading Paused:** " + IntegerToString(currentPauseDuration) + " minutes\n";
                alertMsg += "**Resume Time:** " + TimeToString(pauseStartTime + currentPauseDuration * 60) + "\n";
                alertMsg += "**Action:** Trading Paused";
                
                SendDiscordAlert("⚠️ MINIMUM EQUITY PROTECTION TRIGGERED", alertMsg, 16705372); // Yellow color
            }
        }
    }
}

// +------------------------------------------------------------------+
// | Check High Impact News Event                                     |
// +------------------------------------------------------------------+
void CheckHighImpactNews()
{
    if(!EnableNewsFilter) return;

    ulong newsEventID = 0;
    string newsDetails = IsHighImpactNewsTime(NewsMinutesBefore, NewsMinutesAfter, newsEventID);
    
    if(!isPaused && newsDetails != "" && lastProcessedNewsEventID != newsEventID)
    {
        // Update last processed news event ID
        lastProcessedNewsEventID = newsEventID;
        
        // Trigger the pause mechanism
        isPaused = true;
        pauseStartTime = TimeTradeServer();
        
        // Calculate remaining pause time until event ends
        datetime eventTime = 0;
        datetime currentServerTime = TimeTradeServer();
        MqlCalendarValue values[];

        if(CalendarValueHistory(values, currentServerTime - NewsMinutesBefore * 60, currentServerTime + NewsMinutesAfter * 60 + 120))
        {
            for(int i = 0; i < ArraySize(values); i++)
            {
                if(values[i].event_id == newsEventID)
                {
                    eventTime = values[i].time;
                    break;
                }
            }
        }
        
        if(eventTime > 0)
        {
            int secondsUntilEventEnd = (int)((eventTime + NewsMinutesAfter * 60) - currentServerTime);
            currentPauseDuration = (secondsUntilEventEnd / 60) + 1; // +1 for safety margin
        }
        else
        {
            currentPauseDuration = NewsMinutesAfter; // Fallback
        }
        
        // Update Pause Stats
        totalPauseCount++;
        totalPauseDurationMinutes += currentPauseDuration;
        
        double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
        
        LogPrint("+-----------------------------------------+");
        LogPrint("HIGH-IMPACT NEWS EVENT DETECTED!");
        LogPrint("Server Time: ", TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS));
        LogPrint("Current Equity: $", currentEquity);
        LogPrint("Trading PAUSED for ", currentPauseDuration, " minutes");
        LogPrint("Resume Time: ", TimeToString(pauseStartTime + currentPauseDuration * 60));
        LogPrint("+-----------------------------------------+");
        
        // Send Discord alert with full event details
        if(EnableDiscordAlerts)
        {
            // Add event details
            string alertMsg =  newsDetails + "\n\n";
            
            // Add trading info
            alertMsg += "**Instrument:** " + _Symbol + "\n";
            alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
            alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
            alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
            alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
            alertMsg += "**Trading Paused:** " + IntegerToString(currentPauseDuration) + " minutes\n";
            alertMsg += "**Resume Time:** " + TimeToString(pauseStartTime + currentPauseDuration * 60) + "\n";
            alertMsg += "**Action:** Trading Paused";
            
            SendDiscordAlert("⚠️ HIGH-IMPACT NEWS DETECTED!", alertMsg, 16705372); // Yellow color
        }
    }
}

// +------------------------------------------------------------------+
// | Check Trading Hours                                              |
// +------------------------------------------------------------------+
void CheckTradingHours()
{
    if(!EnableTradingHours) return;
    
    bool currentlyWithinHours = IsWithinTradingHours();
    
    // Check for transition from outside to inside trading hours (Trading Started)
    if(isOutsideTradingHours && currentlyWithinHours)
    {
        isOutsideTradingHours = false;

        double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
        
        LogPrint("+-----------------------------------------+");
        LogPrint("TRADING HOURS STARTED");
        LogPrint("Server Time: ", TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS));
        LogPrint("Trading Period: ", TradingStartTime, " - ", TradingEndTime);
        LogPrint("Current Equity: $", currentEquity);
        LogPrint("+-----------------------------------------+");
        
        // Send Discord alert for trading started
        if(EnableDiscordAlerts)
        {
            string alertMsg = "**Instrument:** " + _Symbol + "\n";
            alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
            alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
            alertMsg += "**Trading Period:** " + TradingStartTime + " - " + TradingEndTime + "\n";
            alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
            alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
            alertMsg += "**Action:** Trading Started";
            
            SendDiscordAlert("🟢 TRADING HOURS STARTED!", alertMsg, 5763719); // Green color
        }
    }
    // Check for transition from inside to outside trading hours (Trading Paused)
    else if(!isOutsideTradingHours && !currentlyWithinHours)
    {
        isOutsideTradingHours = true;

        double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
        
        LogPrint("+-----------------------------------------+");
        LogPrint("TRADING HOURS ENDED");
        LogPrint("Server Time: ", TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS));
        LogPrint("Trading Period: ", TradingStartTime, " - ", TradingEndTime);
        LogPrint("Current Equity: $", currentEquity);
        LogPrint("+-----------------------------------------+");
        
        // Send Discord alert for trading paused
        if(EnableDiscordAlerts)
        {
            string alertMsg = "**Instrument:** " + _Symbol + "\n";
            alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
            alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
            alertMsg += "**Trading Period:** " + TradingStartTime + " - " + TradingEndTime + "\n";
            alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
            alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
            alertMsg += "**Action:** Trading Stopped";
            
            SendDiscordAlert("🔴 TRADING HOURS ENDED!", alertMsg, 15158332); // Red color
            
            // Send Daily Report
            SendTradeReport();
        }
    }
}

// +------------------------------------------------------------------+
// | Check Market Close Time                                          |
// +------------------------------------------------------------------+
void CheckMarketClose()
{
    if(!EnableMarketCloseFilter || MinutesBeforeClose <= 0) return;
    
    MqlDateTime dt;
    TimeCurrent(dt);
    ENUM_DAY_OF_WEEK dayOfWeek = (ENUM_DAY_OF_WEEK)dt.day_of_week;
    
    datetime from, to;
    datetime currentTime = TimeCurrent();
    
    if(SymbolInfoSessionQuote(_Symbol, dayOfWeek, 0, from, to))
    {
        int secondsUntilClose = (int)(to - currentTime);
        int minutesUntilClose = secondsUntilClose / 60;
        
        if(minutesUntilClose > 0 && minutesUntilClose <= MinutesBeforeClose)
        {
            // Send alert once per session
            if(!marketCloseAlertSent && EnableDiscordAlerts)
            {
                double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
                
                string alertMsg = "**Instrument:** " + _Symbol + "\n";
                alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
                alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
                alertMsg += "**Market Closes In:** " + IntegerToString(minutesUntilClose) + " minutes\n";
                alertMsg += "**Market Close Time:** " + TimeToString(to, TIME_DATE|TIME_MINUTES) + "\n";
                alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
                alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
                alertMsg += "**Action:** Stopped Opening New Positions";
                
                SendDiscordAlert("⏰ MARKET CLOSING SOON", alertMsg, 16776960); // Yellow
                marketCloseAlertSent = true;
            }
            
            LogPrint("Market closes in ", minutesUntilClose, " minutes. Not opening new positions.");
            isNearMarketClose = true;
            return; // Already in warning window, no need to check further
        }
        
        // Reset when outside warning period
        if(minutesUntilClose > MinutesBeforeClose)
        {
            isNearMarketClose = false;
            marketCloseAlertSent = false; // Also reset alert flag for next session
            return;
        }
        
        // Current time is past session 0 close — check session 1
        if(currentTime >= to)
        {
            datetime from2, to2;
            if(SymbolInfoSessionQuote(_Symbol, dayOfWeek, 1, from2, to2))
            {
                secondsUntilClose = (int)(to2 - currentTime);
                minutesUntilClose = secondsUntilClose / 60;
                
                if(minutesUntilClose > 0 && minutesUntilClose <= MinutesBeforeClose)
                {
                    LogPrint("Market closes in ", minutesUntilClose, " minutes. Not opening new positions.");
                    isNearMarketClose = true;
                    return;
                }
                
                if(minutesUntilClose > MinutesBeforeClose)
                {
                    isNearMarketClose = false;
                    return;
                }
            }
        }
    }
    
    // No valid session found or market is closed
    isNearMarketClose = false;
}
// +------------------------------------------------------------------+

// +------------------------------------------------------------------+
// | Check for Leverage Changes                                       |
// +------------------------------------------------------------------+
void CheckLeverageChange()
{
    // Skip if feature is disabled
    if(!EnableLeveragePause) return;
    
    long currentLeverage = AccountInfoInteger(ACCOUNT_LEVERAGE);
    
    // Leverage changed from initial
    if(currentLeverage != initialLeverage && !isLeverageDiffFromInitial)
    {
        isLeverageDiffFromInitial = true;
        
        double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
        
        LogPrint("+-----------------------------------------+");
        LogPrint("LEVERAGE CHANGE DETECTED - TRADING PAUSED");
        LogPrint("Initial Leverage: 1:", (int)initialLeverage);
        LogPrint("Current Leverage: 1:", (int)currentLeverage);
        LogPrint("Current Equity: $", currentEquity);
        LogPrint("Trading will resume when leverage returns to 1:", (int)initialLeverage);
        LogPrint("+-----------------------------------------+");
        
        // Send Discord alert
        if(EnableDiscordAlerts)
        {
            string alertMsg = "**Instrument:** " + _Symbol + "\n";
            alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
            alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
            alertMsg += "**Initial Leverage:** 1:" + IntegerToString((int)initialLeverage) + "\n";
            alertMsg += "**Current Leverage:** 1:" + IntegerToString((int)currentLeverage) + "\n";
            alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
            alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
            alertMsg += "**Action:** Trading Paused";
            
            SendDiscordAlert("⚠️ LEVERAGE CHANGE - TRADING PAUSED", alertMsg, 16705372); // Orange color
        }
        
        CloseAllPositions(); 
    }
    // Leverage returned to initial - check if we're paused due to leverage (currentPauseDuration == 0)
    else if(currentLeverage == initialLeverage && isLeverageDiffFromInitial && currentPauseDuration == 0)
    {
        isLeverageDiffFromInitial = false;
        
        double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
        
        LogPrint("+-----------------------------------------+");
        LogPrint("LEVERAGE RESTORED - TRADING RESUMED");
        LogPrint("Leverage: 1:", (int)currentLeverage);
        LogPrint("Current Equity: $", currentEquity);
        LogPrint("+-----------------------------------------+");
        
        // Send Discord alert
        if(EnableDiscordAlerts)
        {
            string alertMsg = "**Instrument:** " + _Symbol + "\n";
            alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
            alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
            alertMsg += "**Leverage:** 1:" + IntegerToString((int)currentLeverage) + "\n";
            alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
            alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
            alertMsg += "**Action:** Trading Resumed";
            
            SendDiscordAlert("▶️ LEVERAGE RESTORED - TRADING RESUMED", alertMsg, 3066993); // Blue color
        }
    }
}

// +------------------------------------------------------------------+
// | Check and Send Trade Report                                      |
// +------------------------------------------------------------------+
void CheckTradeReport()
{   
    if (!EnableReports) return;
    
    datetime serverTime = TimeTradeServer();
    MqlDateTime dt;
    TimeToStruct(serverTime, dt);
    
    bool sendReport = false;
    
    // Check for hourly report
    if (SendReportEveryHour > 0)
    {
        if (lastDailyReportTime == 0)
        {
            lastDailyReportTime = serverTime;
        }
        else if (serverTime - lastDailyReportTime >= SendReportEveryHour * 3600)
        {
            sendReport = true;
        }
    }
    
    // Check for End of Day (23:59) Report
    if(!EnableTradingHours && dt.hour == 23 && dt.min == 59)
    {
        // Check if report already sent today (to avoid spamming in the last minute)
        // lastDailyReportTime checks full timestamp
        MqlDateTime lastReportDt;
        TimeToStruct(lastDailyReportTime, lastReportDt);
        
        if(lastReportDt.day != dt.day)
        {
            sendReport = true;
        }
    }
    
    if (sendReport)
    {
        SendTradeReport();
    }
}

// Get Trade Statistics
void GetTradeStats(TradeStats& daily, TradeStats& allTime) 
{
    // Initialize
    daily.count = 0; daily.won = 0; daily.lost = 0;
    daily.profit = 0; daily.loss = 0;
    daily.maxProfit = 0; daily.minProfit = DBL_MAX;
    daily.maxLoss = 0; daily.minLoss = -DBL_MAX; 

    allTime.count = 0; allTime.won = 0; allTime.lost = 0;
    allTime.profit = 0; allTime.loss = 0;
    allTime.maxProfit = 0; allTime.minProfit = DBL_MAX;
    allTime.maxLoss = 0; allTime.minLoss = -DBL_MAX;

    datetime now = TimeCurrent();
    
    // Trade Stats Session Start Time
    // Start from last report generated, or from start of bot started if no last report
    datetime sessionStartTime = (lastDailyReportTime > 0) ? lastDailyReportTime : startTime;

    if(HistorySelect(0, now)) {
        int deals = HistoryDealsTotal();
        for(int i = 0; i < deals; i++) {
            ulong ticket = HistoryDealGetTicket(i);
            long entryType = HistoryDealGetInteger(ticket, DEAL_ENTRY);
            
            if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol || 
               HistoryDealGetInteger(ticket, DEAL_MAGIC) != MagicNumber) continue;

            double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT) + 
                            HistoryDealGetDouble(ticket, DEAL_SWAP) + 
                            HistoryDealGetDouble(ticket, DEAL_COMMISSION);

            if (entryType == DEAL_ENTRY_OUT || entryType == DEAL_ENTRY_INOUT) {
                // ALL TIME STATS
                allTime.count++;
                if(profit >= 0) {
                    allTime.won++;
                    allTime.profit += profit;
                    if(profit > allTime.maxProfit) allTime.maxProfit = profit;
                    if(profit < allTime.minProfit) allTime.minProfit = profit;
                } else {
                    allTime.lost++;
                    allTime.loss += profit;
                    if(profit < allTime.maxLoss) allTime.maxLoss = profit; 
                    if(profit > allTime.minLoss) allTime.minLoss = profit; 
                }

                // SESSION STATS (Since Last Report or Start)
                datetime dealTime = (datetime)HistoryDealGetInteger(ticket, DEAL_TIME);
                if(dealTime >= sessionStartTime) {
                    daily.count++;
                    if(profit >= 0) {
                        daily.won++;
                        daily.profit += profit;
                        if(profit > daily.maxProfit) daily.maxProfit = profit;
                        if(profit < daily.minProfit) daily.minProfit = profit;
                    } else {
                        daily.lost++;
                        daily.loss += profit;
                        if(profit < daily.maxLoss) daily.maxLoss = profit;
                        if(profit > daily.minLoss) daily.minLoss = profit;
                    }
                }
            }
        }
    }
    
    // Calculate Averages and fix Min/Max initialization if no trades
    // All Time
    if(allTime.won > 0) allTime.avgProfit = allTime.profit / allTime.won; else { allTime.avgProfit = 0; allTime.minProfit = 0; }
    if(allTime.lost > 0) allTime.avgLoss = allTime.loss / allTime.lost; else { allTime.avgLoss = 0; allTime.minLoss = 0; allTime.maxLoss = 0; }
    
    // Daily
    if(daily.won > 0) daily.avgProfit = daily.profit / daily.won; else { daily.avgProfit = 0; daily.minProfit = 0; }
    if(daily.lost > 0) daily.avgLoss = daily.loss / daily.lost; else { daily.avgLoss = 0; daily.minLoss = 0; daily.maxLoss = 0; }
}

// Send Daily Report
void SendTradeReport() 
{
    if(!EnableDiscordAlerts) return;

    double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double deposit = initialBalance;
    
    TradeStats dailyStats;
    TradeStats allTimeStats;
    GetTradeStats(dailyStats, allTimeStats);
    
    // Session net profit
    double sessionNetProfit = dailyStats.profit + dailyStats.loss; // loss is already negative
    double sessionNetPercent = (balance > 0) ? (sessionNetProfit / balance) * 100.0 : 0.0;
    
    // All time net profit
    double allTimeNetProfit = allTimeStats.profit + allTimeStats.loss;
    double allTimeNetPercent = (deposit > 0) ? (allTimeNetProfit / deposit) * 100.0 : 0.0;
    
    // All time profit/loss percentages (kept for existing lines)
    double profitPercent = (balance > 0) ? (allTimeStats.profit / balance) * 100.0 : 0.0;
    double lossPercent = (balance > 0) ? (allTimeStats.loss / balance) * 100.0 : 0.0;
    
    // Duration
    long durationSeconds = TimeCurrent() - startTime;
    int days = (int)(durationSeconds / 86400);
    int hours = (int)((durationSeconds % 86400) / 3600);
    int minutes = (int)((durationSeconds % 3600) / 60);
    string durationStr = "";
    if(days > 0) durationStr += IntegerToString(days) + "d ";
    if(hours > 0) durationStr += IntegerToString(hours) + "h ";
    durationStr += IntegerToString(minutes) + "m";
    
    // Report Interval Duration
    long reportInterval = (lastDailyReportTime > 0) ? (TimeCurrent() - lastDailyReportTime) : durationSeconds;
    int rHours = (int)(reportInterval / 3600);
    int rMinutes = (int)((reportInterval % 3600) / 60);
    string reportDurationStr = "";
    if(rHours > 0) reportDurationStr += IntegerToString(rHours) + "h ";
    reportDurationStr += IntegerToString(rMinutes) + "m";

    string alertMsg = "**Instrument:** " + _Symbol + "\n";
    alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
    alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
    alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
    alertMsg += "**Previous Report Equity:** $" + DoubleToString(lastReportEquity, 2) + "\n";
    alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
    alertMsg += "**Initial Balance:** $" + DoubleToString(deposit, 2) + "\n";
    alertMsg += "**Current Balance:** $" + DoubleToString(balance, 2) + "\n\n";
    
    alertMsg += "**Trades:** " + IntegerToString(dailyStats.count) + "\n";
    alertMsg += "**Won:** " + IntegerToString(dailyStats.won) + "\n";
    alertMsg += "**Lost:** " + IntegerToString(dailyStats.lost) + "\n";
    alertMsg += "**Profit:** $" + DoubleToString(dailyStats.profit, 2) + "\n";
    alertMsg += "**Loss:** $" + DoubleToString(dailyStats.loss, 2) + "\n";
    alertMsg += "**Net Profit:** $" + DoubleToString(sessionNetProfit, 2) + " (" + DoubleToString(sessionNetPercent, 2) + "%)\n\n";
    
    alertMsg += "**All Time Trades:** " + IntegerToString(allTimeStats.count) + "\n";
    alertMsg += "**All Time Won:** " + IntegerToString(allTimeStats.won) + "\n";
    alertMsg += "**All Time Lost:** " + IntegerToString(allTimeStats.lost) + "\n";
    alertMsg += "**All Time Profit:** $" + DoubleToString(allTimeStats.profit, 2) + " (" + DoubleToString(profitPercent, 2) + "%)\n";
    alertMsg += "**All Time Loss:** $" + DoubleToString(allTimeStats.loss, 2) + " (" + DoubleToString(lossPercent, 2) + "%)\n";
    alertMsg += "**All Time Net Profit:** $" + DoubleToString(allTimeNetProfit, 2) + " (" + DoubleToString(allTimeNetPercent, 2) + "%)\n\n";
    
    alertMsg += "**Average Profit:** $" + DoubleToString(allTimeStats.avgProfit, 2) + "\n";
    alertMsg += "**Largest Profit:** $" + DoubleToString(allTimeStats.maxProfit, 2) + "\n";
    alertMsg += "**Smallest Profit:** $" + DoubleToString(allTimeStats.minProfit, 2) + "\n";
    alertMsg += "**Average Loss:** $" + DoubleToString(allTimeStats.avgLoss, 2) + "\n";
    alertMsg += "**Largest Loss:** $" + DoubleToString(allTimeStats.maxLoss, 2) + "\n";
    alertMsg += "**Smallest Loss:** $" + DoubleToString(allTimeStats.minLoss, 2) + "\n\n";
    
    alertMsg += "**Pauses Triggered:** " + IntegerToString(totalPauseCount) + "\n";
    alertMsg += "**Total Paused Duration:** " + DoubleToString(totalPauseDurationMinutes, 0) + " minutes" + "\n";
    alertMsg += "**Report Generated For:** " + reportDurationStr + "\n";
    alertMsg += "**Run Duration:** " + durationStr + "\n";
    
    SendDiscordAlert("📊 TRADE REPORT", alertMsg, 16776960); // Yellow/Gold color
    
    lastDailyReportTime = TimeCurrent();
    lastReportEquity = currentEquity;
}
// +------------------------------------------------------------------+

// +------------------------------------------------------------------+
// | Algo Trading MT5                                                 |
// +------------------------------------------------------------------+
void CheckAlgoTradingStatus()
{
    bool currentStatus = TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
   
   // Detect status change
   if(currentStatus != algoTradingStatus)
   {
      if(currentStatus)
      {
        LogPrint("Algo Trading has been ENABLED");

        double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
        double balance = AccountInfoDouble(ACCOUNT_BALANCE);

        string alertMsg = "**Instrument:** " + _Symbol + "\n";
        alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
        alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
        alertMsg += "**Trading Hours:** " + (EnableTradingHours ? TradingStartTime + " - " + TradingEndTime + "\n" : "DISABLED\n");
        alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
        alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
        alertMsg += "**Current Balance:** $" + DoubleToString(balance, 2) + "\n";
        alertMsg += "**Initial Balance:** $" + DoubleToString(initialBalance, 2) + "\n";
        alertMsg += "**Action:** Trading Started (Algo Trading Enabled)";
        
        SendDiscordAlert("🟢 AUTOMATED TRADING STARTED", alertMsg, 5763719); // Green color
      }
      else
      {
        LogPrint("Algo Trading has been DISABLED");

        double currentEquity = AccountInfoDouble(ACCOUNT_EQUITY);
        double balance = AccountInfoDouble(ACCOUNT_BALANCE);

        string alertMsg = "**Instrument:** " + _Symbol + "\n";
        alertMsg += "**Timeframe:** " + EnumToString(_Period) + "\n";
        alertMsg += "**Server Time:** " + TimeToString(TimeTradeServer(), TIME_DATE|TIME_SECONDS) + "\n";
        alertMsg += "**Trading Hours:** " + (EnableTradingHours ? TradingStartTime + " - " + TradingEndTime + "\n" : "DISABLED\n");
        alertMsg += "**Current Equity:** $" + DoubleToString(currentEquity, 2) + "\n";
        alertMsg += "**Peak Equity:** $" + DoubleToString(peakEquity, 2) + "\n";
        alertMsg += "**Current Balance:** $" + DoubleToString(balance, 2) + "\n";
        alertMsg += "**Initial Balance:** $" + DoubleToString(initialBalance, 2) + "\n";
        alertMsg += "**Action:** Trading Stopped (Algo Trading Disabled)";
        
        SendDiscordAlert("🔴 AUTOMATED TRADING STOPPED", alertMsg, 15158332); // Green color
      }
      
      // Update status
      algoTradingStatus = currentStatus;
   }
}

// Toggle  disable algo trading in MT5
void DisableAlgoTrading()
{
    bool Status = (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED);
    
    if(Status)
    {
        HANDLE hChart = (HANDLE)ChartGetInteger(ChartID(), CHART_WINDOW_HANDLE);
        PostMessageW(GetAncestor(hChart, GA_ROOT), WM_COMMAND, MT_WMCMD_EXPERTS, 0);
    }
}

// +------------------------------------------------------------------+
// | Send Discord alert via webhook                                   |
// +------------------------------------------------------------------+
bool SendDiscordAlert(string title, string message, int embedColor = 3447003)
{
    if(!EnableDiscordAlerts || DiscordWebhookURL == "") return false;

    // Escape special characters in message
    StringReplace(message, "\\", "\\\\");
    StringReplace(message, "\"", "\\\"");
    StringReplace(message, "\n", "\\n");
    
    // Build JSON payload
    string json = "";
    json += "{\"embeds\":[{";
    json += "\"title\":\"" + title + "\",";
    json += "\"description\":\"" + message + "\",";
    json += "\"color\":" + IntegerToString(embedColor) + ",";
    json += "\"footer\":{\"text\":\"Nyao Scalper v43.0\"}";
    json += "}]}";
    
    // Prepare HTTP request
    char post[];
    char result[];
    string headers = "Content-Type: application/json\r\n";
    string resultHeaders = "";
    int timeout = 5000;
    
    // Convert JSON to char array
    StringToCharArray(json, post, 0, WHOLE_ARRAY, CP_UTF8);
    ArrayResize(post, ArraySize(post) - 1); // Remove null terminator

    // Send webhook
    int res = WebRequest("POST", DiscordWebhookURL, headers, timeout, post, result, resultHeaders);

    if(res == 200 || res == 204)
    {
        LogPrint("Discord alert sent: ", title);
        return true;
    }
    else
    {
        LogPrint("Discord ERROR: ", res);
        LogPrint("Payload: ", json);
        LogPrint("Response: ", CharArrayToString(result));
        LogPrint("MT5 Error: ", GetLastError());
        return false;
    }
}

// +------------------------------------------------------------------+
// | Check and Test Discord Alert                                     |
// +------------------------------------------------------------------+
void CheckDiscordAlert() 
{
    if(DiscordWebhookURL == "")
    {
        Print("WARNING: Discord alerts enabled but webhook URL is empty!");
    }
    else if(StringFind(DiscordWebhookURL, "https://discord.com/api/webhooks/") != 0 &&
            StringFind(DiscordWebhookURL, "https://discordapp.com/api/webhooks/") != 0)
    {
        Print("WARNING: Discord webhook URL format may be incorrect!");
    }
    else
    {   
        CheckAlgoTradingStatus();
    }
}

// +------------------------------------------------------------------+
// | Update On-Chart Dashboard                                        |
// +------------------------------------------------------------------+
void DrawDashboardLabel(string name, string text, int x, int y, int fontSize, color clr, bool bold = false)
{
    if(ObjectFind(0, name) < 0)
    {
        ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
        ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
        ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
        ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
        ObjectSetInteger(0, name, OBJPROP_BACK, false);
        ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
        ObjectSetInteger(0, name, OBJPROP_SELECTED, false);
        ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
        ObjectSetInteger(0, name, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
    }
    
    ObjectSetString(0, name, OBJPROP_TEXT, text);
    ObjectSetInteger(0, name, OBJPROP_FONTSIZE, fontSize);
    ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
    ObjectSetString(0, name, OBJPROP_FONT, bold ? "Arial Bold" : "Arial");
}

void UpdateDashboard()
{
    // Clear old comment based dashboard
    Comment("");

    // Layout Constants
    int startX = 20;
    int startY = 20;
    int lineHeight = 18;
    int headersize = 10;
    int textsize = 9;
    int detailsSize = 8;
    
    color colorHeader = clrGold;
    color colorText = clrWhite;
    color colorBuy = clrLime;
    color colorSell = clrRed;
    color colorNeutral = clrGray;
    color colorBg = C'30,30,30';
    color colorBorder = clrGold;

    int currentY = startY;

    // Header
    DrawDashboardLabel("NyaoDash_Title", "Nyao Scalper v43.0", startX, currentY, 11, colorHeader, true);
    currentY += lineHeight + 5;

    // Status logic
    string status = "Active";
    color statusColor = clrLime;
    if(isPaused) { status = "PAUSED (" + IntegerToString(currentPauseDuration) + "m)"; statusColor = clrOrange; }
    else if(isOutsideTradingHours) { status = "Closed (Time)"; statusColor = clrGray; }
    else if(targetEquityReached) { status = "STOPPED (Target)"; statusColor = clrRed; }
    else if(minimumEquityReached) { status = "STOPPED (Min Equity)"; statusColor = clrRed; }

    DrawDashboardLabel("NyaoDash_Status", "Status: " + status, startX, currentY, textsize, statusColor, true);
    currentY += lineHeight;

    // Account Info
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);
    double equityDrop = (peakEquity > 0) ? ((peakEquity - equity) / peakEquity) * 100.0 : 0.0;
    
    DrawDashboardLabel("NyaoDash_Bal", StringFormat("Balance: $%.2f", balance), startX, currentY, textsize, colorText);
    currentY += lineHeight;
    DrawDashboardLabel("NyaoDash_Eq", StringFormat("Equity: $%.2f", equity), startX, currentY, textsize, colorText);
    currentY += lineHeight;
    DrawDashboardLabel("NyaoDash_Peak", StringFormat("Peak: $%.2f (Drop: %.1f%%)", peakEquity, equityDrop), startX, currentY, textsize, colorText);
    currentY += lineHeight + 5;

    // Hedge Chain status (only when feature enabled)
    if(atlasRuntime.enableHedgeChain)
    {
        // Count distinct active chains, total chain legs, and deepest cycle in progress
        ulong dashIds[];
        int dashChains = 0;
        int dashLegs = 0;
        int dashMaxCycle = 0;
        for(int h = 0; h < managedPositionCount; h++)
        {
            ulong r = managedPositions[h].chainId;
            if(r == 0) continue;
            dashLegs++;
            if(managedPositions[h].cycleNum > dashMaxCycle) dashMaxCycle = managedPositions[h].cycleNum;
            bool seen = false;
            for(int k = 0; k < dashChains; k++) if(dashIds[k] == r) { seen = true; break; }
            if(!seen) { ArrayResize(dashIds, dashChains + 1); dashIds[dashChains++] = r; }
        }

        DrawDashboardLabel("NyaoDash_Hedge",
                           StringFormat("Hedge Chains: %d (legs %d, cycle %d/%d)", dashChains, dashLegs, dashMaxCycle,
                                        (HedgeMaxCycles > 0 ? HedgeMaxCycles : 0)),
                           startX, currentY, textsize, dashChains > 0 ? clrOrange : colorText);
        currentY += lineHeight + 5;
    }
    else
    {
        // Hide stale label when feature is toggled off
        ObjectDelete(0, "NyaoDash_Hedge");
    }

    // Signal Strength (Smoothed - Unified)
    SignalStrength buyStrength = GetSignalStrength(ORDER_TYPE_BUY);
    SignalStrength sellStrength = GetSignalStrength(ORDER_TYPE_SELL);
    
    // Raw closed-candle scores for reference
    double rawBuyScore = ComputeRawScore(ORDER_TYPE_BUY, 1);
    double rawSellScore = ComputeRawScore(ORDER_TYPE_SELL, 1);

    DrawDashboardLabel("NyaoDash_SigHead", "SIGNAL STRENGTH:", startX, currentY, headersize, colorHeader, true);
    currentY += lineHeight;

    string reqBuyText = StringFormat("Min Buy: %.2f", atlasRuntime.minBuySignalScore);
    DrawDashboardLabel("NyaoDash_ReqBuy", reqBuyText, startX, currentY, detailsSize, colorText);
    currentY += lineHeight;

    string reqSellText = StringFormat("Min Sell: %.2f", atlasRuntime.minSellSignalScore);
    DrawDashboardLabel("NyaoDash_ReqSell", reqSellText, startX, currentY, detailsSize, colorText);
    currentY += lineHeight;

    // Buy Row
    string buyText = StringFormat("BUY SCORE: %.2f", buyStrength.finalScore);
    DrawDashboardLabel("NyaoDash_Buy", buyText, startX, currentY, textsize, buyStrength.finalScore > sellStrength.finalScore ? colorBuy : colorText, true);
    currentY += lineHeight;

    string rawBuyText = StringFormat("Raw (Closed): %.2f", rawBuyScore);
    DrawDashboardLabel("NyaoDash_CurrentBuy", rawBuyText, startX, currentY, detailsSize, colorText);
    currentY += lineHeight;
    
    string buyDet = StringFormat("%s", buyStrength.reasoning);
    DrawDashboardLabel("NyaoDash_BuyDet", buyDet, startX, currentY, detailsSize, colorText);
    currentY += lineHeight + 2;

    // Sell Row
    string sellText = StringFormat("SELL SCORE: %.2f", sellStrength.finalScore);
    DrawDashboardLabel("NyaoDash_Sell", sellText, startX, currentY, textsize, sellStrength.finalScore > buyStrength.finalScore ? colorSell : colorText, true);
    currentY += lineHeight;

    string rawSellText = StringFormat("Raw (Closed): %.2f", rawSellScore);
    DrawDashboardLabel("NyaoDash_CurrentSell", rawSellText, startX, currentY, detailsSize, colorText);
    currentY += lineHeight;

    string sellDet = StringFormat("%s",sellStrength.reasoning);
    DrawDashboardLabel("NyaoDash_SellDet", sellDet, startX, currentY, detailsSize, colorText);
    currentY += lineHeight + 10;

    // Statistics
    TradeStats daily, allTime;
    GetTradeStats(daily, allTime);
    double allTimeNetProfit = allTime.profit + allTime.loss;
    
    DrawDashboardLabel("NyaoDash_StatHead", "STATISTICS:", startX, currentY, headersize, colorHeader, true);
    currentY += lineHeight;
    
    DrawDashboardLabel("NyaoDash_Trades", StringFormat("Trades: %d (W:%d / L:%d)", allTime.count, allTime.won, allTime.lost), startX, currentY, textsize, colorText);
    currentY += lineHeight;

    DrawDashboardLabel("NyaoDash_PL", StringFormat("Profit: $%.2f | Loss: $%.2f", allTime.profit, allTime.loss), startX, currentY, textsize, colorText);
    currentY += lineHeight;
    
    color profitColor = allTimeNetProfit >= 0 ? colorBuy : colorSell;
    DrawDashboardLabel("NyaoDash_Net", StringFormat("NET PROFIT: $%.2f", allTimeNetProfit), startX, currentY, textsize, profitColor, true);
}
// +------------------------------------------------------------------+