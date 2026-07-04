//+------------------------------------------------------------------+
//|                                 MetaTrader Manager Report Plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "HistoryProfitLoss.h"
//+------------------------------------------------------------------+
//| Sort DailyRecord by bank-group-login                             |
//+------------------------------------------------------------------+
static int SortDailyLoginTime(const void *left,const void *right)
  {
   DailyReport *lhs=(DailyReport*)left;
   DailyReport *rhs=(DailyReport*)right;
//---
   int res=lhs->login-rhs->login;
   if(res==0) res=lhs->ctm-rhs->ctm;
//---
   return(res);
  }
//+------------------------------------------------------------------+
//| History Raw Report                                               |
//+------------------------------------------------------------------+
BOOL CHistoryProfitLoss::GenerateHTML(const ReportParams* params)
  {
   DailyReport *daily=NULL,*rep=NULL;
   int          total=0,login=0,count=0,result=TRUE,i;
   char         tmp[256]="";
   double       equity_prev=0.0,profit_prev=0.0,profit_loss=0.0;
   const UserRecord *user=NULL;
//--- checks
   if(params==NULL)                                 return(FALSE);
   if(params->filepath[0]==0)                       return(FALSE);
   if((daily=(DailyReport*)params->buffer)==NULL)   return(FALSE);
   if((total=params->buffer_size/sizeof(*daily))<1) return(FALSE);
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
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//--- table header
   fprintf(m_file,"<tr bgcolor=#c0c0c0 align=right>");
   fprintf(m_file,"<td align=left>Date</td>"
                  "<td align=left>Login</td>"
                  "<td>Balance</td>"
                  "<td>Credit</td>"
                  "<td nowrap>Previous Equity</td>"
                  "<td nowrap>Present Equity</td>"
                  "<td nowrap>Profit/Loss</td>");
   fprintf(m_file,"</tr>\n");
//--- sort rows
   if(total>1) qsort(daily,total,sizeof(daily[0]),SortDailyLoginTime);
//--- generate report
   for(i=0,rep=daily,login=0,count=0;i<total;i++,rep++)
     {
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
      //--- new login
      if(login!=rep->login)
        {
         //--- check user
         login=rep->login;
         if((user=UserRecordGet(params,login))==NULL) continue;
         //--- clear profit/loss
         profit_loss=0.0;
         //--- check last daily record for login
         if((i==total-1 || login!=(rep+1)->login) &&
            user->regdate>=rep->ctm-86400)
           {
            //--- new account registered
            equity_prev=rep->equity-rep->profit_closed-rep->profit;
            profit_prev=0;
           }
         else
           {
            //--- save previous equity and profit
            equity_prev=rep->equity;
            profit_prev=rep->profit;
            continue;
           }
        }
      //--- check user
      if(user==NULL) continue;
      //--- last daily record for login
      if(i==total-1 || login!=(rep+1)->login)
        {
         //--- calculate daily profil/loss
         profit_loss+=rep->profit_closed+rep->profit-profit_prev;
         //--- background color
         if((count&1)==0) fprintf(m_file,"<tr align=right>");
         else             fprintf(m_file,"<tr align=right bgcolor=#e0e0e0>");
         count++;
         //--- row
         fprintf(m_file,"<td align=left>%s</td>",FormatDateTime(rep->ctm,tmp,sizeof(tmp)-1,FALSE));
         fprintf(m_file,"<td align=left>%d</td>",rep->login);
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->balance,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->credit, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(equity_prev, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(rep->equity, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(profit_loss, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"</tr>\n");
         continue;
        }
      //--- calculate daily profit/loss
      profit_loss+=rep->profit_closed+rep->profit-profit_prev;
      profit_prev=rep->profit;
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
BOOL CHistoryProfitLoss::GenerateCSV(const ReportParams* params)
  {
   DailyReport *daily=NULL,*rep=NULL;
   int          total=0,login=0,result=TRUE,i;
   char         tmp[256];
   double       equity_prev=0.0,profit_prev=0.0,profit_loss=0.0;
   const UserRecord *user=NULL;
//--- checks
   if(params==NULL)                                 return(FALSE);
   if(params->filepath[0]==0)                       return(FALSE);
   if((daily=(DailyReport*)params->buffer)==NULL)   return(FALSE);
   if((total=params->buffer_size/sizeof(*daily))<1) return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- report header
   fprintf(m_file,"%s for '%s'",m_info.name,params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"\n");
   fprintf(m_file,"Date;Login;Balance;Credit;Previous Equity;Present Equity;Profit/Loss\n");
//--- sort rows
   if(total>1) qsort(daily,total,sizeof(daily[0]),SortDailyLoginTime);
//--- generate report
   for(i=0,rep=daily,login=0;i<total;i++,rep++)
     {
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
      //--- new login
      if(login!=rep->login)
        {
         //--- check user
         login=rep->login;
         if((user=UserRecordGet(params,login))==NULL) continue;
         //--- clear profit/loss
         profit_loss=0.0;
         //--- check last daily record for login
         if((i==total-1 || login!=(rep+1)->login) &&
            user->regdate>=rep->ctm-86400)
           {
            //--- new account registered
            equity_prev=rep->equity-rep->profit_closed-rep->profit;
            profit_prev=0;
           }
         else
           {
            //--- save previous equity and profit
            equity_prev=rep->equity;
            profit_prev=rep->profit;
            continue;
           }
        }
      //--- check user
      if(user==NULL) continue;
      //---
      if(i==total-1 || login!=(rep+1)->login)
        {
         profit_loss+=rep->profit_closed+rep->profit-profit_prev;
         //--- row
         fprintf(m_file,"%s;",FormatDateTime(rep->ctm,tmp,sizeof(tmp)-1,FALSE));
         fprintf(m_file,"%d;",rep->login);
         fprintf(m_file,"%s;",ToMoney(rep->balance,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"%s;",ToMoney(rep->credit, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"%s;",ToMoney(equity_prev, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"%s;",ToMoney(rep->equity, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"%s;",ToMoney(profit_loss, 2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"\n");
         continue;
        }
      //---
      profit_loss+=rep->profit_closed+rep->profit-profit_prev;
      profit_prev=rep->profit;
     }
//---
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
