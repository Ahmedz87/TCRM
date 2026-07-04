//+------------------------------------------------------------------+
//|                                        Commission reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once

#define WINVER         0x0501
#define _WIN32_IE      0x0600
#define WIN32_LEAN_AND_MEAN

//---
#include <windows.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <limits.h>
#include <new.h>

//--- special for /analyze
#pragma warning(push)
#pragma warning(disable : 6387 6011)
#include <strsafe.h>
#pragma warning(pop)

//--- macros
#define TERMINATE_STR(str) str[_countof(str)-1]=0;
#define COPY_STR(dst,src) { strncpy(dst,src,_countof(dst)-1); dst[_countof(dst)-1]=0; }

//---
#include "ReportsPlugIn.h"
#include "Reports\Report.h"
#include "Reports\CommissionReport.h"
#include "Config\Configuration.h"
#include "common\common.h"
//--- global
extern char ExtProgramPath[256];
extern char ExtProgramFile[256];
//+------------------------------------------------------------------+
