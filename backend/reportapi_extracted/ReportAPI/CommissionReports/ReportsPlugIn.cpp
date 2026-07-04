//+------------------------------------------------------------------+
//|                                        Commission reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+

#include "stdafx.h"
//--- double numbers formatting
#define SIG_NEGATIVE    ('-')
#define SIG_DECIMAL     ('.')
#define SIG_THOUSAND    (' ')
//--- trade commands
static const char  *ExtOperations[9]={ "buy","sell","buy limit","sell limit",
   "buy stop","sell stop","balance","credit","error" };
//---
static const double ExtDecimalArray[9] ={ 1.0, 10.0, 100.0, 1000.0, 10000.0, 100000.0, 1000000.0, 10000000.0, 100000000.0 };  // положительные степени 10
//---
static const double ExtHalf=0.5000001;
static const double ExtMinusHalf=-0.5000001;
static const double ExtZero=0.0;
//+------------------------------------------------------------------+
//| Get command name                                                 |
//+------------------------------------------------------------------+
LPCSTR GetCmd(const int cmd)
  {
//--- checks
   if(cmd<0 || cmd>7) return(ExtOperations[8]);
//---
   return(ExtOperations[cmd]);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
double Decimals(const int digits)
  {
   if(digits>=0 && digits<8) return(ExtDecimalArray[digits]);
   else                      return(1.0);
  }
//+------------------------------------------------------------------+
//| Get UserRecord by login                                          |
//+------------------------------------------------------------------+
const UserRecord *UserRecordGet(const ReportParams *params, int login)
  {
//--- checks
   if(params->users==NULL) return(NULL);
//--- find user by login
   for(int i=0;i<params->users_total;i++)
      if(params->users[i].login==login) return &params->users[i];
//---
   return(NULL);
  }
//+------------------------------------------------------------------+
//| Get ConSymbol by symbol name                                     |
//+------------------------------------------------------------------+
const ConSymbol *SymbolGet(const ReportParams *params, LPCSTR symbol)
  {
//--- checks
   if(symbol==NULL || symbol[0]==0|| params->symbols==NULL) return(NULL);
//--- find symbol by name
   for(int i=0;i<params->symbols_total;i++)
      if(_stricmp(params->symbols[i].symbol, symbol)==0) return &params->symbols[i];
//---
   return(NULL);
  }
//+------------------------------------------------------------------+
//| Get ConGroup by group name                                       |
//+------------------------------------------------------------------+
const ConGroup *GroupGet(const ReportParams *params,LPCSTR group)
  {
//--- checks
   if(group==NULL || group[0]==0|| params->user_groups==NULL) return(NULL);
//--- find group by name
   for(int i=0;i<params->user_groups_total;i++)
      if(_stricmp(params->user_groups[i].group, group)==0) return &params->user_groups[i];
//---
   return(NULL);
  }
//+------------------------------------------------------------------+
//| Convert double to string                                         |
//+------------------------------------------------------------------+
LPSTR ToSym(char *pricebuf,const double price,int digits)
  {
   char *cp=NULL;
//--- checks
   if(pricebuf==NULL) return(pricebuf);
//--- convert using sprintf
   if(digits>0) digits++;
   if(digits>8) digits=8;
   sprintf(pricebuf,"%.8lf",price);
   if((cp=strstr(pricebuf,"."))!=NULL) *(cp+digits)=0;
//---
   return(pricebuf);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
LPSTR ToSymExt(char *psz,const double val,int digits,int more)
  {
   static  const char cd[]={ '0','1','2','3','4','5','6','7','8','9',0 };
   const   int maxchars=250;
   double  valdec=0.0;
   __int64 val64 =0;
   char    tmp[256]="",*cp=NULL,*dst=NULL;
   int     i,negative=FALSE,len=0;
//--- checks
   if(psz==NULL) return(psz);
   if(digits<0) digits=0;
   if(more  <0) more  =0;
   if(digits+more>7) more=7-digits;
   digits+=more;
//--- multiply to integer keeping significant digits
   valdec=val*ExtDecimalArray[digits];
//--- check __int64 overflow
   if(valdec>=_I64_MAX/10000 || valdec<=_I64_MIN/10000)
     {
      //--- __int64 overflow, use slow sprintf method
      //--- format string
      StringCchPrintfA(tmp,sizeof(tmp)-1,"%%.%dlf",digits);
      //--- do format
      if(digits>0) digits++;
      StringCchPrintfA(psz,maxchars,tmp,val);
      if((cp=strrchr(psz,'.'))!=NULL) { *cp=SIG_DECIMAL; *(cp+digits)=0; }
      //--- cut trailing zeros
      cp=psz+strlen(psz)-1;
      for(i=0; i<more; i++) if(*cp=='0') *cp--=0;
      if(*cp=='.') *cp--=0;
      //--- done
      return(psz);
     }
//--- fast format using integer division
   if(val<0.0)
     {
      negative=TRUE;
      val64=-__int64(valdec-0.5);
     }
   else
     {
      val64=__int64(valdec+0.5);
     }
   cp=tmp;
//--- fill in reverse string using %10
//--- fractional part
   if(digits>0)
     {
      for(i=0; i<digits; i++)
        {
         *cp++=cd[val64%10];
         val64/=10;
        }
      *cp++=SIG_DECIMAL;
     }
//--- integer part
   *cp++=cd[val64%10]; //--- for 0.** case
   for(val64/=10; val64!=0; val64/=10) *cp++=cd[val64%10];
   if(negative) *cp++=SIG_NEGATIVE;
   *cp=0;
//--- check maxchars
   len=cp-tmp;
   if(len>=maxchars+1) { *psz=0; return(psz); }
//--- reverse result string
   dst=psz; cp=tmp+len-1;
   while(cp>=tmp) *dst++=*cp--;
   *dst--=0;
//--- cut trailing zeros
   for(i=0; i<more; i++) if(*dst=='0') *dst--=0;
   if(*dst=='.') *dst--=0;
//--- done
   return(psz);
  }
//+------------------------------------------------------------------+
//| Convert double to money                                          |
//+------------------------------------------------------------------+
LPSTR ToMoney(const double val,int digits,char *psz,const int maxchars)
  {
   double  valdec=0.0;
   __int64 val64 =0;
   static const char cd[]={ '0','1','2','3','4','5','6','7','8','9',0 };
   char    tmp[256]="",*cp=NULL,*pt=NULL,*dst=NULL;
   int     i,negative=FALSE,len=0,delta=0;
//--- checks
   if(psz==NULL || maxchars<1) return(psz);
   if(digits<0 || digits>=8) digits=0;
//--- multiply to integer keeping significant digits
   valdec=val*ExtDecimalArray[digits];
//--- check __int64 overflow
   if(valdec>=_I64_MAX/10000 || valdec<=_I64_MIN/10000)
     {
      //--- __int64 overflow, use slow sprintf method
      if(digits>0) digits++;
      StringCchPrintfA(tmp,sizeof(tmp)-10,"%.8lf",val);
      if((cp=strrchr(tmp,'.'))!=NULL) { *cp=SIG_DECIMAL; *(cp+digits)=0; }
      //--- check maxchars
      len=strlen(tmp);
      if(cp!=NULL && *cp!=0)
        {
         if(val<0.0) delta=(cp-tmp-1)%3;
         else        delta=(cp-tmp)%3;
         pt=cp; len+=(cp-tmp)/3;
        }
      else
        {
         if(val<0.0) delta=(len-1)%3;
         else        delta=len%3;
         pt=tmp+len-1; len+=len/3;
        }
      if(len>=maxchars-1) { *psz=0; return(psz); }
      if(delta==0) delta=3;
      if(val<0.0)  delta+=1;
      //--- integer part with thousand separators
      dst=psz; cp=tmp;
      for(i=0; i<delta; ++i) *dst++=*cp++;
      delta=3;
      while(cp<pt)
        {
         *dst++=SIG_THOUSAND;
         for(i=0; i<delta; ++i) *dst++=*cp++;
        }
      //--- fractional part
      while(*cp!=0) *dst++=*cp++;
      *dst=0;
      //--- done
      return(psz);
     }
//--- fast format using integer division
   if(val<0.0)
     {
      negative=TRUE;
      val64=-__int64(valdec-0.5);
     }
   else
     {
      val64=__int64(valdec+0.5);
     }
   cp=tmp;
//--- fill in reverse string using %10
//--- fractional part
   if(digits>0)
     {
      for(i=0; i<digits; i++)
        {
         *cp++=cd[val64%10];
         val64/=10;
        }
      *cp++=SIG_DECIMAL;
     }
//--- integer part
   *cp++=cd[val64%10]; //--- for 0.** case
   for(val64/=10,i=1; val64!=0; val64/=10,++i)
     {
      if(i%3==0) *cp++=SIG_THOUSAND;
      *cp++=cd[val64%10];
     }
   if(negative) *cp++=SIG_NEGATIVE;
   *cp=0;
//--- check maxchars
   len=cp-tmp;
   if(len>=maxchars+1) { *psz=0; return(psz); }
//--- reverse result string
   dst=psz; cp=tmp+len-1;
   while(cp>=tmp) *dst++=*cp--;
   *dst=0;
//--- done
   return(psz);
  }
//+------------------------------------------------------------------+
//| Normalize double                                                 |
//+------------------------------------------------------------------+
double NormalizeDouble(double val,int digits)
  {
   if(digits<0) digits=0;
   if(digits>8) digits=8;
//---
   const double p=ExtDecimalArray[digits];
   return((val>=0.0) ? (double(__int64(val*p+0.5000001))/p) : (double(__int64(val*p-0.5000001))/p));
  }
//+------------------------------------------------------------------+
//| Convert date/time to string                                      |
//+------------------------------------------------------------------+
LPCSTR FormatDateTime(time_t ctm,LPSTR sz,int maxchars,BOOL bUseTime,BOOL bUseSec)
  {
   tm *ptm=gmtime(&ctm);
//---
   if(sz==NULL || maxchars<11 || ptm==NULL) return(NULL);
//---
   if(bUseTime)
     {
      if(bUseSec) StringCchPrintfA(sz,maxchars,"%04d.%02d.%02d %02d:%02d:%02d",ptm->tm_year+1900,ptm->tm_mon+1,ptm->tm_mday,ptm->tm_hour,ptm->tm_min,ptm->tm_sec);
      else        StringCchPrintfA(sz,maxchars,"%04d.%02d.%02d %02d:%02d",ptm->tm_year+1900,ptm->tm_mon+1,ptm->tm_mday,ptm->tm_hour,ptm->tm_min);
     }
   else StringCchPrintfA(sz,maxchars,"%04d.%02d.%02d",ptm->tm_year+1900,ptm->tm_mon+1,ptm->tm_mday);
//---
   return(sz);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
