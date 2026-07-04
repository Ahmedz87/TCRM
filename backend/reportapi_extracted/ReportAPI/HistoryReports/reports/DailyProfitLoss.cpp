//+------------------------------------------------------------------+
//|                                 MetaTrader Manager Report Plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "DailyProfitLoss.h"
//+------------------------------------------------------------------+
//| History Raw Report                                               |
//+------------------------------------------------------------------+
BOOL CDailyProfitLoss::GenerateHTML(const ReportParams* params)
  {
   DailyReport *daily=NULL,*rep=NULL,*prev=NULL;
   int          total=0,i,count,result=TRUE;
   char         tmp[256]="";
//--- checks
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*daily))<1)  return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- generation
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".date  { mso-number-format:\"yyyy\\.mm\\.dd\"; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=99%%>\n");
   fprintf(m_file,"<tr><td colspan=10><font size=2><b>%s</b> for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from+86400,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-86400,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//--- table header
   fprintf(m_file,"<tr bgcolor=#c0c0c0 align=right>");
   fprintf(m_file,"<td align=left>Time</td>"
                  "<td align=left>Login</td>"
                  "<td>Balance</td>"
                  "<td>Credit</td>"
                  "<td nowrap>Previous Equity</td>"
                  "<td nowrap>Present Equity</td>"
                  "<td nowrap>Daily Profit/Loss</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   daily=(DailyReport*)params->buffer;
//--- skip first day reports
   for(i=0,rep=daily;i<total;i++,rep++)
      if(rep->ctm>params->group.from+86400)
         break;
//--- generate report
   for(count=0;i<total;i++,count++,rep++)
     {
      //--- background color
      if((count&1)==0) fprintf(m_file,"<tr align=right>");
      else             fprintf(m_file,"<tr align=right bgcolor=#e0e0e0>");
      //--- find previous daily report
      for(prev=rep-1;prev>=daily;prev--)
         if(prev->login==rep->login)
            break;
      if(prev<daily || prev->login!=rep->login)
         prev=NULL;
      //--- row
      fprintf(m_file,"<td align=left class=date>%s</td>",FormatDateTime(rep->ctm,tmp,sizeof(tmp)-1,FALSE));
      fprintf(m_file,"<td align=left>%d</td>",rep->login);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->balance,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->credit, 2,tmp,sizeof(tmp)-1));
      if(prev!=NULL) fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(prev->equity,2,tmp,sizeof(tmp)-1));
      else           fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(0.0,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->equity,2,tmp,sizeof(tmp)-1));
      if(prev!=NULL) 
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->profit_closed+rep->profit-prev->profit,2,tmp,sizeof(tmp)-1));
      else 
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->profit_closed+rep->profit,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"</tr>\n");
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
     }
//---
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CDailyProfitLoss::GenerateCSV(const ReportParams* params)
  {
   DailyReport *daily=NULL,*rep=NULL,*prev=NULL;
   int          total=0,i,result=TRUE;
   char         tmp[256];
//--- checks
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*daily))<1)  return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- report header
   fprintf(m_file,"%s for '%s' from ",m_info.name,params->group.name);
   FormatDateTime(params->group.from+86400,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file,"%s",tmp);
   fprintf(m_file," to ");
   FormatDateTime(params->group.to-86400,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file,"%s",tmp);
   fprintf(m_file,"\n");
   fprintf(m_file,"Time;Login;Balance;Credit;Previous Equity;Present Equity;Daily Profit/Loss\n");
//--- report rows
   daily=(DailyReport*)params->buffer;
//--- skip first day reports
   for(i=0,rep=daily;i<total;i++,rep++)
      if(rep->ctm>params->group.from+86400)
         break;
//--- generate report
   for(;i<total;i++,rep++)
     {
      //--- find previous daily report
      for(prev=rep-1;prev>=daily;prev--)
         if(prev->login==rep->login)
            break;
      if(prev<daily || prev->login!=rep->login)
         prev=NULL;
      //--- row
      fprintf(m_file,"%s;",FormatDateTime(rep->ctm,tmp,sizeof(tmp)-1,FALSE));
      fprintf(m_file,"%d;",rep->login);
      fprintf(m_file,"%s;",ToMoney(rep->balance,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"%s;",ToMoney(rep->credit, 2,tmp,sizeof(tmp)-1));
      if(prev!=NULL) fprintf(m_file,"%s;",ToMoney(prev->equity,2,tmp,sizeof(tmp)-1));
      else           fprintf(m_file,"%s;",ToMoney(0.0,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"%s;",ToMoney(rep->equity,2,tmp,sizeof(tmp)-1));
      if(prev!=NULL) 
         fprintf(m_file,"%s;",ToMoney(rep->profit_closed+rep->profit-prev->profit,2,tmp,sizeof(tmp)-1));
      else 
         fprintf(m_file,"%s;",ToMoney(rep->profit_closed+rep->profit,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"\n");
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
     }
//---
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
