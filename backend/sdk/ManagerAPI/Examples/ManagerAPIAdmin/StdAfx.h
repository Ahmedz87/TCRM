//+------------------------------------------------------------------+
//|                                      MetaTrader Manager API Test |
//|                             Copyright 2000-2026, MetaQuotes Ltd. |
//|                                               www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once

#define WINVER               _WIN32_WINNT_WIN7
#define _WIN32_WINNT         _WIN32_WINNT_WIN7
#define _WIN32_WINDOWS       _WIN32_WINNT_WIN7
#define _WIN32_IE            _WIN32_IE_IE90
#define NTDDI_VERSION        NTDDI_WIN7

#define VC_EXTRALEAN             // Exclude rarely-used stuff from Windows headers

#include <afxwin.h>              // MFC core and standard components
#include <afxext.h>              // MFC extensions
#include <afxdisp.h>             // MFC Automation classes
#include <afxdtctl.h>            // MFC support for Internet Explorer 4 Common Controls
#ifndef _AFX_NO_AFXCMN_SUPPORT
#include <afxcmn.h>              // MFC support for Windows Common Controls
#endif // _AFX_NO_AFXCMN_SUPPORT
#include <afxsock.h>             // MFC socket extensions
//---
#include <math.h>

//--- macros
#define TERMINATE_STR(str)   str[_countof(str)-1]=0;
#define COPY_STR(dst,src)  { strncpy(dst,src,_countof(dst)-1); dst[_countof(dst)-1]=0; }
//{{AFX_INSERT_LOCATION}}
//+------------------------------------------------------------------+
